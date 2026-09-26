import hashlib
import hmac

from app.providers import PROVIDERS
from app.providers.forges import GiteaProvider, GitHubProvider, GitLabProvider

SECRET = "s3cret"
BODY = b'{"ref":"refs/heads/main"}'
MAC = hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()

GITHUB_LIKE = {
    "ref": "refs/heads/main",
    "repository": {"name": "demo"},
    "head_commit": {
        "id": "abc123",
        "message": "feat: x",
        "author": {"name": "Ada"},
        "timestamp": "2026-09-20T10:15:00Z",
        "added": ["a.py"],
        "modified": ["b.py"],
        "removed": [],
    },
    "commits": [{"id": "abc123", "added": ["a.py"], "modified": ["b.py"], "removed": []}],
}

GITLAB = {
    "object_kind": "push",
    "ref": "refs/heads/main",
    "checkout_sha": "def456",
    "user_name": "Ada",
    "project": {"name": "demo", "path_with_namespace": "org/demo"},
    "commits": [
        {"id": "000", "message": "old", "author": {"name": "Bob"}, "added": [], "modified": ["x"], "removed": []},
        {"id": "def456", "message": "feat: y", "author": {"name": "Ada"}, "timestamp": "2026-09-20T10:15:00+02:00", "added": ["a"], "modified": [], "removed": []},
    ],
}


def test_les_trois_forges_sont_enregistrees():
    assert set(PROVIDERS) == {"gitea", "github", "gitlab"}


def test_push_gitea_et_github_partagent_le_format():
    for forge in (GiteaProvider, GitHubProvider):
        e = forge.parse_push(GITHUB_LIKE)
        assert e and e.repository == "demo" and e.branch == "main" and e.commit_id == "abc123"
        assert e.author == "Ada" and e.commits[0]["modified"] == ["b.py"]


def test_push_gitlab_prend_le_commit_checkout():
    e = GitLabProvider.parse_push(GITLAB)
    assert e and e.commit_id == "def456" and e.commit_message == "feat: y" and e.author == "Ada"
    assert e.repository == "demo" and len(e.commits) == 2


def test_evenements_non_push_ignores():
    assert GitHubProvider.parse_push({"zen": "ping"}) is None
    assert GitHubProvider.parse_push({**GITHUB_LIKE, "deleted": True}) is None
    assert GitHubProvider.parse_push({**GITHUB_LIKE, "ref": "refs/tags/v1"}) is None
    assert GitLabProvider.parse_push({**GITLAB, "object_kind": "tag_push"}) is None
    assert GitLabProvider.parse_push({**GITLAB, "checkout_sha": None}) is None


def test_signature_gitea_hex_nu_ou_prefixe():
    assert GiteaProvider.verify_signature(BODY, {"X-Gitea-Signature": MAC}, SECRET)
    assert GiteaProvider.verify_signature(BODY, {"x-hub-signature-256": f"sha256={MAC}"}, SECRET)
    assert not GiteaProvider.verify_signature(BODY, {"X-Gitea-Signature": MAC}, "autre")
    assert not GiteaProvider.verify_signature(BODY, {}, SECRET)


def test_signature_github_prefixee():
    assert GitHubProvider.verify_signature(BODY, {"x-hub-signature-256": f"sha256={MAC}"}, SECRET)
    assert not GitHubProvider.verify_signature(BODY + b" ", {"x-hub-signature-256": f"sha256={MAC}"}, SECRET)


def test_signature_gitlab_jeton_en_clair():
    assert GitLabProvider.verify_signature(BODY, {"x-gitlab-token": SECRET}, SECRET)
    assert not GitLabProvider.verify_signature(BODY, {"x-gitlab-token": "faux"}, SECRET)
    assert not GitLabProvider.verify_signature(BODY, {}, SECRET)
    assert not GitLabProvider.verify_signature(BODY, {"x-gitlab-token": ""}, "")


def test_gitlab_instance_et_api():
    p = GitLabProvider("https://gitlab.example/", "t")
    assert p.base_url == "https://gitlab.example"
    assert p.client.api_url == "https://gitlab.example/api/v4"
    assert GitLabProvider("", "t").base_url == "https://gitlab.com"


def test_github_url_par_defaut():
    assert GitHubProvider("", "t").api_url == "https://api.github.com"
    assert GitHubProvider("https://ghe.corp/api/v3/", "t").api_url == "https://ghe.corp/api/v3"
