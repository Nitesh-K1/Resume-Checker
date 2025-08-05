import spacy
import streamlit as st
import pdfplumber
from docx import Document
import requests
import logging
import re
import json
import base64

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
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        url = f"https://api.github.com/users/{username}/repos"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        repos = response.json()
        projects = []
        for repo in repos:
            # Fetch topics
            topics_url = f"https://api.github.com/repos/{username}/{repo['name']}/topics"
            headers_topics = {"Accept": "application/vnd.github.mercy-preview+json"}
            if token:
                headers_topics["Authorization"] = f"Bearer {token}"
            topics_resp = requests.get(topics_url, headers=headers_topics)
            topics = topics_resp.json().get("names", []) if topics_resp.status_code == 200 else []

            # Fetch README
            readme_url = f"https://api.github.com/repos/{username}/{repo['name']}/readme"
            readme_resp = requests.get(readme_url, headers=headers)
            readme_content = ""
            if readme_resp.status_code == 200:
                readme_data = readme_resp.json()
                if 'content' in readme_data:
                    readme_content = base64.b64decode(readme_data['content']).decode('utf-8')

            projects.append({
                "name": repo.get("name", ""),
                "description": repo.get("description", ""),
                "language": repo.get("language", ""),
                "topics": topics,
                "readme": readme_content,
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

def analyze_candidate_fit(resume_text, github_repos, job_description):
    # Extract skills from all three sources
    resume_skills = set(extract_skills(resume_text))
    job_skills = set(extract_skills(job_description))

    github_skills = set()
    for repo in github_repos:
        # Combine all text from the repo to search for skills
        repo_text = " ".join([
            repo.get("name", ""),
            repo.get("description", ""),
            repo.get("language", ""),
            " ".join(repo.get("topics", [])),
            repo.get("readme", "")
        ]).lower()

        for skill in KNOWN_SKILLS:
            if skill in repo_text:
                github_skills.add(skill)

    # --- Analysis ---
    # Skills the candidate has that are required for the job
    matched_skills = resume_skills.intersection(job_skills)

    # Skills required for the job that the candidate does not have on their resume
    missing_skills = job_skills - resume_skills

    # Skills on the resume that are also found on GitHub
    verified_skills = resume_skills.intersection(github_skills)

    # Skills on the resume that are NOT found on GitHub
    unverified_skills = resume_skills - github_skills

    return {
        "matched_skills": list(matched_skills),
        "missing_skills": list(missing_skills),
        "verified_skills": list(verified_skills),
        "unverified_skills": list(unverified_skills),
        "job_skills": list(job_skills),
        "resume_skills": list(resume_skills),
        "github_skills": list(github_skills)
    }

def display_analysis_results(result):
    st.subheader("Candidate Fit Analysis")

    job_skills = result.get("job_skills", [])
    resume_skills = result.get("resume_skills", [])
    matched_skills = result.get("matched_skills", [])
    missing_skills = result.get("missing_skills", [])
    verified_skills = result.get("verified_skills", [])
    unverified_skills = result.get("unverified_skills", [])

    # --- Scoring ---
    score = 0
    if job_skills:
        score = (len(matched_skills) / len(job_skills)) * 100

    # --- Display Score and Summary ---
    st.progress(int(score) / 100)
    if score >= 75:
        st.success(f"**Excellent Fit!** (Score: {score:.2f}%)")
    elif score >= 50:
        st.info(f"**Good Fit.** (Score: {score:.2f}%)")
    elif score >= 25:
        st.warning(f"**Partial Fit.** (Score: {score:.2f}%)")
    else:
        st.error(f"**Not a Strong Fit.** (Score: {score:.2f}%)")

    # --- Detailed Breakdown ---
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Job Skill Match")
        st.metric("Required Skills Met", f"{len(matched_skills)} / {len(job_skills)}")
        if matched_skills:
            st.markdown("✅ **Matched Skills:**")
            st.write(", ".join(sorted(matched_skills)))
        if missing_skills:
            st.markdown("❌ **Missing Skills:**")
            st.write(", ".join(sorted(missing_skills)))

    with col2:
        st.markdown("#### GitHub Verification")
        st.metric("Resume Skills Verified", f"{len(verified_skills)} / {len(resume_skills)}")
        if verified_skills:
            st.markdown("✅ **Verified Skills:**")
            st.write(", ".join(sorted(verified_skills)))
        if unverified_skills:
            st.markdown("⚠️ **Unverified Skills:**")
            st.write(", ".join(sorted(unverified_skills)))

    # --- Expander for Full Details ---
    with st.expander("Show Detailed Skill Lists"):
        st.json(result)

    # --- Download Button ---
    st.download_button(
        "Download Full Report (JSON)",
        data=json.dumps(result, indent=2),
        file_name="candidate_analysis_report.json",
        mime="application/json"
    )

# Streamlit Interface
st.title("Comprehensive Resume Analyzer")
st.markdown("Analyze your resume against a job description and verify your skills with your GitHub profile.")

resume_file = st.file_uploader("Upload Resume (PDF/DOCX/TXT)", type=["pdf", "docx", "txt"])
job_description = st.text_area("Paste Job Description Here*", height=200, placeholder="e.g., 'We are looking for a Python developer with experience in Django...'")

col1, col2 = st.columns(2)
with col1:
    github_url = st.text_input("GitHub Profile URL*", placeholder="https://github.com/username")
with col2:
    github_token = st.text_input("GitHub Token (Optional)", type="password")

if st.button("Analyze"):
    if not resume_file or not github_url or not job_description:
        st.warning("Please upload a resume, paste a job description, and provide a valid GitHub profile URL.")
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
                    st.text_area("Resume Text", resume_text, height=150)

                    github_repos = get_github_repos(username, github_token)
                    if not github_repos:
                        st.warning("No public repositories found or failed to fetch data.")
                    else:
                        # Run the new analysis
                        analysis_result = analyze_candidate_fit(resume_text, github_repos, job_description)

                        # Display the new, formatted results
                        display_analysis_results(analysis_result)
