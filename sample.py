import os
import requests
import base64
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

github_token = os.getenv("GITHUB_TOKEN")

headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github+json"
}

def scan_structure(repo: str) -> dict:
    if "github.com" in repo:
        repo = repo.split("github.com")
        if len(repo) <= 1:
            print("Invalid github url")
            return
        repo = repo[1]

    owner_and_repo_name = get_owner_and_repo_name(repo)
    default_branch = get_default_branch(owner_and_repo_name["owner"], owner_and_repo_name["repo_name"])

    if default_branch == "":
        return

    repo_tree = get_repo_tree(owner_and_repo_name["owner"], owner_and_repo_name["repo_name"], default_branch)
    if len(repo_tree.keys()) < 1:
        return

    tree_checks = check_tree(repo_tree["tree"])
    branch_checks = check_branches(owner_and_repo_name["owner"], owner_and_repo_name["repo_name"])
    commits = check_commits(owner_and_repo_name["owner"], owner_and_repo_name["repo_name"])
    contributor_checks = check_contributors(owner_and_repo_name["owner"], owner_and_repo_name["repo_name"])
    secrets_check = check_secrets(owner_and_repo_name["owner"], owner_and_repo_name["repo_name"],repo_tree["tree"])

    owner    = owner_and_repo_name["owner"]
    repo_name = owner_and_repo_name["repo_name"]

    print( {
        "repo": f"{owner}/{repo_name}" ,
        "scanned_at": datetime.now(timezone.utc),
        "tree_checks": tree_checks,
        "branch_checks": branch_checks,
        "commits": commits,
        "contributor_checks": contributor_checks,
        "secrets_check": secrets_check
    } )

def get_owner_and_repo_name(repo: str) -> dict:
    repo = repo.strip("/")
    parts = repo.split("/")
    if len(parts) == 1:
        return []
    return {
        "owner":     parts[0],
        "repo_name": parts[1]
    }

def get_default_branch(owner: str, repo: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        response = requests.get(url=url, headers=headers)
        if response.status_code == 404:
            print("❌ Repo not found — check owner/repo name or repo may be private")
            return ""
        data = response.json()
        return data["default_branch"]
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed — check your internet")
        return ""

def get_repo_tree(owner: str, repo: str, default_branch: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    try:
        response = requests.get(url=url, headers=headers)
        if response.status_code == 404:
            print("❌ Repo not found — check owner/repo name or repo may be private")
            return {}
        data = response.json()
        return data
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed — check your internet")
        return {}
    
def check_tree(tree: dict) -> dict:
    readme_exists = False
    license_exists = False
    gitignore_exists = False
    ci_config_exists = False
    test_directory_exists = False
    env_file_exists = False

    tests_paths = ["tests/", "test/", "spec/", "__tests__/"]
    config_files = [".github/workflows/", ".travis.yml", ".circleci/", "jenkinsfile", ".gitlab-ci.yml"]

    for tree_path in tree:
        path = tree_path["path"].lower()

        if "readme" in path:
            readme_exists = True
        if ".env" in path:
            env_file_exists = True
        if "license" in path:
            license_exists = True
        if "gitignore" in path:
            gitignore_exists = True
        if any(test in path for test in tests_paths):
            test_directory_exists = True
        if any(test in path for test in config_files):
            ci_config_exists = True
    return {
        "readme":{
            "exists": readme_exists
        },
        "LICENSE":{
            "exists": license_exists
        },
        "gitignore":{
            "exists": gitignore_exists
        },
        "ci_config":{
            "exists": ci_config_exists
        },
        "test_directory":{
            "exists": test_directory_exists
        },
        "env_files":{
            "exists": env_file_exists 
        }
    }

def check_branches(owner: str, repo:str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/branches"
    try:
        response = requests.get(url=url, headers=headers)
        if response.status_code == 404:
            print("❌ Repo not found — check owner/repo name or repo may be private")
            return {}
        data = response.json()
        number_of_branches = len(data)
        stale_branches = get_stale_branches(data)

        return {
            "total_branches": number_of_branches,
            "stale_branches":{
                "total": len(stale_branches),
                "branches": stale_branches
            }
        }
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed — check your internet")
        return {}
    
def get_stale_branches(branches: list) -> list:
    stale_branches = []
    for branch in branches:
        url = branch["commit"]["url"]
        try:
            response = requests.get(url=url, headers=headers)
            if response.status_code == 404:
                print("❌ Commit not found — check your repo for proper commit")
                return stale_branches
            data = response.json()
            commit_date = data["commit"]["author"]["date"]
            commit_datetime = datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_inactive = (now - commit_datetime).days
            if days_inactive > 60:
                stale_branches.append({
                    "name": branch["name"],
                    "last_commit_date": commit_date,
                    "days_inactive": days_inactive
                })
        except requests.exceptions.ConnectionError:
            print("❌ Connection failed — check your internet")
    return stale_branches

def check_commits(owner: str, repo: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    try:
        response = requests.get(url=url, headers=headers)
        if response.status_code == 404:
            print("❌ Commits not found — check your repo for proper commit")
            return {}
        data = response.json()
        last_commit_date = data[0]["commit"]["author"]["date"]
        last_commit_datetime = datetime.fromisoformat(last_commit_date.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_since_last_commit = (now - last_commit_datetime).days
        return {
            "last_commit_date": last_commit_date,
            "days_since_last_commit": days_since_last_commit
        }
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed — check your internet")
        return {}
    
def check_contributors(owner: str, repo: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
    try:
        response = requests.get(url=url, headers=headers)
        if response.status_code == 404:
            print("❌ Commits not found — check your repo for proper commit")
            return {}
        data = response.json()
        contributor_count = len(data)
        contributors = []
        for contributor in data:
            contributors.append({
                "name": contributor["login"],
                "contributions": contributor["contributions"]
            })
        return {
            "contributor_count": contributor_count,
            "contributors": contributors
        }

    except requests.exceptions.ConnectionError:
        print("❌ Connection failed — check your internet")
        return {}
            
def check_secrets(owner: str, repo: str, tree: list) -> dict:
    SENSITIVE_FILES = [
        "config.py", "settings.py",  "config.json", "config.yml", "config.yaml"
    ]

    target_files = [
        tree_path["path"] for tree_path in tree
        if tree_path["path"].split('/')[-1].lower() in SENSITIVE_FILES
    ]

    all_findings = []
    for file_path in target_files:
        content = get_file_content(owner, repo, file_path)
        if content == "":
            continue
        findings = scan_for_secrets(content, file_path)
        all_findings.extend(findings)
    return {
        "scanned_files": target_files,
        "secrets_found": len(all_findings) > 0,
        "findings": all_findings
    }

def get_file_content(owner: str, repo: str, file_path: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    try:
        response = requests.get(url=url, headers=headers)
        if response.status_code == 404:
            print(f"❌ File not found: {file_path}")
            return ""
        data = response.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed — check your internet")
        return ""
    
def scan_for_secrets(content: str, file_path: str) -> dict:
    findings = []
    SECRET_PATTERMS = [
        r'API_KEY\s*=\s*["\']?.{8,}',
        r'API_SECRET\s*=\s*["\']?.{8,}',
        r'SECRET_KEY\s*=\s*["\']?.{8,}',
        r'SECRET\s*=\s*["\']?.{8,}',
        r'PASSWORD\s*=\s*["\']?.{8,}',
        r'PASSWD\s*=\s*["\']?.{8,}',
        r'TOKEN\s*=\s*["\']?.{8,}',
        r'ACCESS_TOKEN\s*=\s*["\']?.{8,}',
        r'aws_access_key_id\s*=\s*["\']?.{8,}',
        r'aws_secret_access_key\s*=\s*["\']?.{8,}',
        r'private_key\s*=\s*["\']?.{8,}'
    ]
    lines = content.splitlines()

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("/"):
            continue
        for pattern in SECRET_PATTERMS:
            if re.search(pattern, stripped, re.IGNORECASE):
                findings.append({
                    "file": file_path,
                    "line": line_number,
                    "pattern_matches": pattern
                })
    return findings
if __name__ == "__main__":
    github_url = input("Enter your repo here: ")
    scan_structure(github_url)
