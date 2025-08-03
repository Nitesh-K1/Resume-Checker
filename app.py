import spacy
import streamlit as st
import pdfplumber
from docx import Document
import requests
import logging
import re
import json

nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
logging.basicConfig(filename="app.log", level=logging.ERROR)

# Predefined skill set for matching
KNOWN_SKILLS = [
    "python", "java", "javascript", "node.js", "react", "angular", "docker",
    "kubernetes", "aws", "azure", "git", "terraform", "sql", "mongodb",
    "html", "css", "c++", "c#", "go", "php", "ruby"
]

def extract_username_from_url(url):
    match = re.search(r"github\.com/([^/]+)/?$", url)
    return match.group(1) if match else None

@st.cache_data(ttl=3600)
def get_github_repos(username, token=None):
    headers = {"Accept": "application/vnd.github.mercy-preview+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        url = f"https://api.github.com/users/{username}/repos"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        repos = response.json()
        projects = []
        for repo in repos:
            topics_url = f"https://api.github.com/repos/{username}/{repo['name']}/topics"
            topics_resp = requests.get(topics_url, headers=headers)
            topics = topics_resp.json().get("names", []) if topics_resp.status_code == 200 else []
            projects.append({
                "name": repo.get("name", ""),
                "description": repo.get("description", ""),
                "language": repo.get("language", ""),
                "topics": topics,
            })
        return projects
    except Exception as e:
        logging.error(f"GitHub Error: {e}")
        return []

def extract_text(uploaded_file):
    try:
        if uploaded_file.name.endswith('.pdf'):
            with pdfplumber.open(uploaded_file) as pdf:
                return " ".join((page.extract_text() or "") for page in pdf.pages)
        elif uploaded_file.name.endswith('.docx'):
            return " ".join(p.text for p in Document(uploaded_file).paragraphs)
        else:
            return uploaded_file.getvalue().decode('utf-8')
    except Exception as e:
        logging.error(f"File Extraction Error: {e}")
        return ""

def extract_skills(text):
    text_lower = text.lower()
    return [skill for skill in KNOWN_SKILLS if skill in text_lower]

def extract_projects(text):
    # Look for words after "project", "worked on", or "developed"
    projects = set()
    patterns = [
        r'project\s*[:\-]\s*(.+)',
        r'worked on\s+(.+)',
        r'developed\s+(.+?)\s+(?:using|with|in|for)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        projects.update([m.strip().split('.')[0] for m in matches])
    return list(projects)

def analyze_resume_vs_github(resume_skills, resume_projects, github_repos):
    matched_skills = set()
    matched_projects = set()
    github_languages = {repo["language"].lower() for repo in github_repos if repo["language"]}
    github_repo_titles = {repo["name"].lower() for repo in github_repos}

    for skill in resume_skills:
        if skill.lower() in github_languages:
            matched_skills.add(skill)

    for proj in resume_projects:
        for repo_title in github_repo_titles:
            if proj.lower() in repo_title:
                matched_projects.add(proj)

    return {
        "matched_skills": list(matched_skills),
        "unmatched_skills": list(set(resume_skills) - matched_skills),
        "matched_projects": list(matched_projects),
        "unmatched_projects": list(set(resume_projects) - matched_projects),
    }

def evaluate_candidate(result):
    total = len(result["matched_skills"]) + len(result["matched_projects"])
    possible = total + len(result["unmatched_skills"]) + len(result["unmatched_projects"])
    score_percent = (total / possible) * 100 if possible > 0 else 0

    if score_percent >= 70:
        return "✅ Good Fit", score_percent
    elif score_percent >= 40:
        return "⚠️ Partial Fit", score_percent
    else:
        return "❌ Not a Fit", score_percent

# Streamlit Interface
st.title("Resume vs GitHub Analyzer - Fit Checker")
st.markdown("Upload your resume and check if your GitHub aligns with your claimed skills and projects.")

resume_file = st.file_uploader("Upload Resume (PDF/DOCX/TXT)", type=["pdf", "docx", "txt"])

col1, col2 = st.columns(2)
with col1:
    github_url = st.text_input("GitHub Profile URL*", placeholder="https://github.com/username")
with col2:
    github_token = st.text_input("GitHub Token (Optional)", type="password")

if st.button("Analyze"):
    if not resume_file or not github_url:
        st.warning("Please upload a resume and provide a valid GitHub profile URL.")
    else:
        username = extract_username_from_url(github_url)
        if not username:
            st.error("Invalid GitHub URL. Format should be: https://github.com/username")
        else:
            with st.spinner("Analyzing your profile..."):
                resume_text = extract_text(resume_file)
                if not resume_text:
                    st.error("Unable to extract text from the uploaded file.")
                else:
                    st.subheader("Extracted Resume Text Preview")
                    st.text_area("Resume Text", resume_text, height=250)
                    github_repos = get_github_repos(username, github_token)
                    if not github_repos:
                        st.warning("No public repositories found or failed to fetch data.")
                    else:
                        resume_skills = extract_skills(resume_text)
                        resume_projects = extract_projects(resume_text)
                        analysis_result = analyze_resume_vs_github(resume_skills, resume_projects, github_repos)
                        fit_status, score = evaluate_candidate(analysis_result)

                        st.subheader("Candidate Fit Result")
                        st.write(f"**{fit_status}** — Score: **{score:.2f}%**")
                        st.metric("Matched Skills", len(analysis_result["matched_skills"]))
                        st.metric("Matched Projects", len(analysis_result["matched_projects"]))
                        st.markdown("**Matched Skills:**")
                        st.write(", ".join(analysis_result["matched_skills"]) or "None")
                        st.markdown("**Unmatched Skills:**")
                        st.write(", ".join(analysis_result["unmatched_skills"]) or "None")
                        st.markdown("**Matched Projects:**")
                        st.write(", ".join(analysis_result["matched_projects"]) or "None")
                        st.markdown("**Unmatched Projects:**")
                        st.write(", ".join(analysis_result["unmatched_projects"]) or "None")

                        st.download_button(
                            "Download Result as JSON",
                            data=json.dumps({
                                "fit_status": fit_status,
                                "score": score,
                                **analysis_result
                            }, indent=2),
                            file_name="fit_analysis_result.json",
                            mime="application/json"
                        )
