#!/usr/bin/env python3
"""
Helper for autonomous Dale to update Linear tickets via Bash.

Usage:
  python3 linear_update.py status DAL-42 "In Progress"
  python3 linear_update.py status DAL-42 "Done"
  python3 linear_update.py comment DAL-42 "Finished implementing. See commit abc123."
  python3 linear_update.py assign DAL-42 benedict
  python3 linear_update.py assign DAL-42 none
  python3 linear_update.py create "Title here" --description "Details" --labels "SEO,Track B" --priority 3
"""

import json
import os
import sys
import urllib.request
import urllib.error

SECRETS_DIR = "/opt/dale/secrets"
GRAPHQL_URL = "https://api.linear.app/graphql"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _blocklist_path():
    """Resolve state/ticket-blocklist.json via config.json's repo path.

    Falls back to <three-dirs-up>/state/ticket-blocklist.json so the module
    works both on the server (/opt/dale/autonomous/ + /opt/dale/repo/state/)
    and in the dev repo (tools/autonomous/ + state/).
    """
    try:
        with open(CONFIG_PATH) as f:
            repo = json.load(f).get("paths", {}).get("repo")
        if repo:
            candidate = os.path.join(repo, "state", "ticket-blocklist.json")
            if os.path.exists(candidate):
                return candidate
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "state", "ticket-blocklist.json",
    )


def check_blocklist(title, description):
    """Return (pattern, reason) if title+description matches a blocked pattern, else None."""
    try:
        with open(_blocklist_path()) as f:
            blocklist = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    haystack = f"{title}\n{description}".lower()
    for entry in blocklist.get("blocks", []):
        for pattern in entry.get("patterns", []):
            if pattern.lower() in haystack:
                return pattern, entry.get("reason", "(no reason given)")
    return None


def get_token():
    env_path = os.path.join(SECRETS_DIR, "linear.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LINEAR_API_TOKEN="):
                return line.split("=", 1)[1]
    raise ValueError("LINEAR_API_TOKEN not found in linear.env")


def graphql(query, variables=None):
    token = get_token()
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(GRAPHQL_URL, data=body, method="POST", headers={
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "dale-autonomous/2.0",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
        if "errors" in result:
            print(f"GraphQL errors: {result['errors']}", file=sys.stderr)
            sys.exit(1)
        return result.get("data")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_team_id(team_name):
    data = graphql("""
        query($name: String!) {
            teams(filter: { name: { eq: $name } }) {
                nodes { id }
            }
        }
    """, {"name": team_name})
    if not data or not data["teams"]["nodes"]:
        return None
    return data["teams"]["nodes"][0]["id"]


def get_issue_id(identifier):
    """Get internal issue ID from identifier like DAL-42."""
    # Parse team key and number from identifier (e.g. DAL-42)
    parts = identifier.rsplit("-", 1)
    if len(parts) != 2:
        print(f"Invalid identifier format: {identifier}", file=sys.stderr)
        sys.exit(1)
    team_key, number = parts[0], parts[1]

    data = graphql("""
        query($filter: IssueFilter!) {
            issues(filter: $filter, first: 1) {
                nodes { id identifier }
            }
        }
    """, {"filter": {"number": {"eq": int(number)}, "team": {"key": {"eq": team_key}}}})
    if not data or not data["issues"]["nodes"]:
        print(f"Issue {identifier} not found", file=sys.stderr)
        sys.exit(1)
    return data["issues"]["nodes"][0]["id"]


def get_state_id(team_id, state_name):
    """Get the state ID for a given state name on a team."""
    data = graphql("""
        query($teamId: ID!) {
            workflowStates(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name type }
            }
        }
    """, {"teamId": team_id})
    if not data:
        return None
    for state in data["workflowStates"]["nodes"]:
        if state["name"].lower() == state_name.lower():
            return state["id"]
    return None


def get_user_id(name_or_email):
    """Find a user by name or email."""
    data = graphql("""
        query { users { nodes { id name email } } }
    """)
    if not data:
        return None
    for user in data["users"]["nodes"]:
        if (name_or_email.lower() in (user["name"] or "").lower()
                or name_or_email.lower() in (user["email"] or "").lower()):
            return user["id"]
    return None


def get_label_ids(team_id, label_names):
    """Get label IDs by name."""
    data = graphql("""
        query {
            issueLabels { nodes { id name } }
        }
    """)
    if not data:
        return []
    ids = []
    name_map = {l["name"].lower(): l["id"] for l in data["issueLabels"]["nodes"]}
    for name in label_names:
        lid = name_map.get(name.strip().lower())
        if lid:
            ids.append(lid)
        else:
            print(f"Warning: label '{name}' not found", file=sys.stderr)
    return ids


def cmd_status(args):
    if len(args) < 2:
        print("Usage: linear_update.py status DAL-42 'In Progress'", file=sys.stderr)
        sys.exit(1)
    identifier, state_name = args[0], args[1]

    config = load_config()
    team_name = config.get("linear", {}).get("team", "Dale")
    team_id = get_team_id(team_name)
    issue_id = get_issue_id(identifier)
    state_id = get_state_id(team_id, state_name)

    if not state_id:
        print(f"State '{state_name}' not found", file=sys.stderr)
        sys.exit(1)

    data = graphql("""
        mutation($id: String!, $stateId: String!) {
            issueUpdate(id: $id, input: { stateId: $stateId }) {
                issue { identifier state { name } }
            }
        }
    """, {"id": issue_id, "stateId": state_id})

    issue = data["issueUpdate"]["issue"]
    print(f"{issue['identifier']} -> {issue['state']['name']}")


def cmd_comment(args):
    if len(args) < 2:
        print("Usage: linear_update.py comment DAL-42 'Comment text'", file=sys.stderr)
        sys.exit(1)
    identifier, body = args[0], args[1]
    issue_id = get_issue_id(identifier)

    # Always prefix Dale's comments so they're distinguishable from Benedict's
    if not body.startswith("Dale:"):
        body = f"Dale: {body}"

    data = graphql("""
        mutation($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                comment { id }
            }
        }
    """, {"issueId": issue_id, "body": body})
    print(f"Comment added to {identifier}")


def cmd_assign(args):
    if len(args) < 2:
        print("Usage: linear_update.py assign DAL-42 benedict|none", file=sys.stderr)
        sys.exit(1)
    identifier, assignee = args[0], args[1]
    issue_id = get_issue_id(identifier)

    if assignee.lower() == "none":
        graphql("""
            mutation($id: String!) {
                issueUpdate(id: $id, input: { assigneeId: null }) {
                    issue { identifier }
                }
            }
        """, {"id": issue_id})
        print(f"{identifier} -> unassigned")
    else:
        user_id = get_user_id(assignee)
        if not user_id:
            print(f"User '{assignee}' not found", file=sys.stderr)
            sys.exit(1)
        graphql("""
            mutation($id: String!, $userId: String!) {
                issueUpdate(id: $id, input: { assigneeId: $userId }) {
                    issue { identifier assignee { name } }
                }
            }
        """, {"id": issue_id, "userId": user_id})
        print(f"{identifier} -> assigned to {assignee}")


def cmd_create(args):
    if not args:
        print("Usage: linear_update.py create 'Title' [--description '...'] [--labels 'SEO,Tech'] [--priority 3]",
              file=sys.stderr)
        sys.exit(1)

    title = args[0]
    description = ""
    labels_str = ""
    priority = 3  # Normal

    i = 1
    while i < len(args):
        if args[i] == "--description" and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        elif args[i] == "--labels" and i + 1 < len(args):
            labels_str = args[i + 1]
            i += 2
        elif args[i] == "--priority" and i + 1 < len(args):
            priority = int(args[i + 1])
            i += 2
        else:
            i += 1

    # Hard block on prospects/topics Benedict has explicitly closed out.
    # See state/ticket-blocklist.json. This cannot be bypassed by rewording.
    blocked = check_blocklist(title, description)
    if blocked:
        pattern, reason = blocked
        print(
            f"BLOCKED: ticket title/description contains '{pattern}'.\n"
            f"Reason: {reason}\n"
            f"If you believe this is a mistake, ask Benedict to edit state/ticket-blocklist.json.",
            file=sys.stderr,
        )
        sys.exit(2)

    config = load_config()
    team_name = config.get("linear", {}).get("team", "Dale")
    max_backlog = config.get("linear", {}).get("max_backlog", 20)
    team_id = get_team_id(team_name)

    # Check backlog count
    from linear_poller import get_issues_by_state
    backlog = get_issues_by_state(team_id, "backlog")
    if len(backlog) >= max_backlog:
        print(f"Backlog full ({len(backlog)}/{max_backlog}). Cannot create more tickets.", file=sys.stderr)
        sys.exit(1)

    # Get backlog state ID
    state_id = get_state_id(team_id, "Backlog")

    variables = {
        "teamId": team_id,
        "title": title,
        "stateId": state_id,
        "priority": priority,
    }

    mutation_input = "teamId: $teamId, title: $title, stateId: $stateId, priority: $priority"
    var_types = "$teamId: String!, $title: String!, $stateId: String!, $priority: Int!"

    if description:
        variables["description"] = description
        mutation_input += ", description: $description"
        var_types += ", $description: String!"

    # Always add "Dale" label to tickets created by autonomous Dale
    label_names = ["Dale"]
    if labels_str:
        label_names += [l.strip() for l in labels_str.split(",")]
    label_ids = get_label_ids(team_id, label_names)
    if label_ids:
        variables["labelIds"] = label_ids
        mutation_input += ", labelIds: $labelIds"
        var_types += ", $labelIds: [String!]!"

    data = graphql(f"""
        mutation({var_types}) {{
            issueCreate(input: {{ {mutation_input} }}) {{
                issue {{ identifier title state {{ name }} }}
            }}
        }}
    """, variables)

    issue = data["issueCreate"]["issue"]
    print(f"Created {issue['identifier']}: {issue['title']} [{issue['state']['name']}]")
    print(f"Backlog: {len(backlog) + 1}/{max_backlog}")


def cmd_label(args):
    """Add or remove a label from an issue."""
    if len(args) < 3 or args[0] not in ("add", "remove"):
        print("Usage: linear_update.py label add|remove DAL-42 'Label Name'", file=sys.stderr)
        sys.exit(1)
    action, identifier, label_name = args[0], args[1], args[2]
    issue_id = get_issue_id(identifier)

    config = load_config()
    team_name = config.get("linear", {}).get("team", "Dale")
    team_id = get_team_id(team_name)
    label_ids = get_label_ids(team_id, [label_name])
    if not label_ids:
        print(f"Label '{label_name}' not found", file=sys.stderr)
        sys.exit(1)
    label_id = label_ids[0]

    # Get current labels on the issue
    data = graphql("""
        query($id: String!) {
            issue(id: $id) { labels { nodes { id name } } }
        }
    """, {"id": issue_id})
    current_ids = [l["id"] for l in data["issue"]["labels"]["nodes"]]

    if action == "add":
        if label_id in current_ids:
            print(f"{identifier} already has label '{label_name}'")
            return
        new_ids = current_ids + [label_id]
    else:  # remove
        if label_id not in current_ids:
            print(f"{identifier} doesn't have label '{label_name}'")
            return
        new_ids = [lid for lid in current_ids if lid != label_id]

    graphql("""
        mutation($id: String!, $labelIds: [String!]!) {
            issueUpdate(id: $id, input: { labelIds: $labelIds }) {
                issue { identifier labels { nodes { name } } }
            }
        }
    """, {"id": issue_id, "labelIds": new_ids})
    print(f"{identifier}: {'added' if action == 'add' else 'removed'} label '{label_name}'")


COMMANDS = {
    "status": cmd_status,
    "comment": cmd_comment,
    "assign": cmd_assign,
    "create": cmd_create,
    "label": cmd_label,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: linear_update.py <{'|'.join(COMMANDS.keys())}> ...", file=sys.stderr)
        sys.exit(1)

    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
