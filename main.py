import os
import json
import requests
from datetime import datetime
from jinja2 import Template
from itertools import cycle

# Configuration fields
API_USERNAME = ""
API_PASSWORD = ""
SEASON = 2024
EVENT_CODE = "BCVI"
TOURNAMENT_LEVEL = "qualification"  # Options: "practice" or "qualification"
CACHE_FILE = "schedule_cache.json"
SCOUTING_MEMBERS = [
    "Alex Carter", "Jordan Smith", "Taylor Johnson", "Morgan Davis", "Casey Brown",
    "Riley Wilson", "Jamie Anderson", "Drew Thompson", "Peyton Martinez", "Quinn Moore",
    "Cameron Taylor", "Reese Clark", "Logan Lewis", "Avery Lee", "Charlie Hall"
]

MIN_TEAMS_PER_MEMBER = 4
MIN_MEMBERS_PER_TEAM = 2
LUNCH_BREAK_THRESHOLD_MINUTES = 60
GAP_UNDERLINE_THRESHOLD_MINUTES = 15
EXCLUDED_TEAMS = [9999, 8888, 5516]


def fetch_schedule():
    url = f"https://frc-api.firstinspires.org/v3.0/{SEASON}/schedule/{EVENT_CODE}?tournamentLevel={TOURNAMENT_LEVEL}"
    response = requests.get(url, auth=(API_USERNAME, API_PASSWORD))
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch schedule: {response.status_code} {response.reason}")


def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return None


def assign_scouting(schedule, members, min_teams, min_members):
    print("DEBUG: Building assignments for non-excluded teams...")
    assignments = {member: [] for member in members}
    team_assignments = {}

    # Collect only non-excluded teams
    for match in schedule:
        for team in match["teams"]:
            if team not in EXCLUDED_TEAMS:
                if team not in team_assignments:
                    team_assignments[team] = []

    print(f"DEBUG: Found {len(team_assignments)} non-excluded teams: {list(team_assignments.keys())}\n")

    members_cycle = cycle(members)
    # Assign each team to min_members members
    for team in team_assignments:
        while len(team_assignments[team]) < min_members:
            member = next(members_cycle)
            if team not in assignments[member]:
                assignments[member].append(team)
                team_assignments[team].append(member)
        print(f"DEBUG: Team {team} => {team_assignments[team]}")

    print("\nDEBUG: After ensuring min_members, assignments dictionary:")
    for m in assignments:
        print(f"  {m}: {assignments[m]}")

    # Ensure each member has at least min_teams
    teams_cycle = cycle(team_assignments.keys())
    for member in assignments:
        while len(assignments[member]) < min_teams:
            team = next(teams_cycle)
            if team not in assignments[member]:
                assignments[member].append(team)
                team_assignments[team].append(member)

    print("\nDEBUG: After ensuring min_teams, assignments dictionary (pre-purge):")
    for m in assignments:
        print(f"  {m}: {assignments[m]}")

    # Purge excluded
    for member in assignments:
        original_count = len(assignments[member])
        assignments[member] = [t for t in assignments[member] if t not in EXCLUDED_TEAMS]
        if len(assignments[member]) < original_count:
            print(f"DEBUG: Purged excluded from {member}. => {assignments[member]}")

    print("\nDEBUG: Final assignment dictionary (post-purge):")
    for m in assignments:
        print(f"  {m}: {assignments[m]}")

    return assignments, team_assignments

def generate_member_schedule(member, schedule, team_assignments, assigned_teams, generation_info):
    """
    1. Exactly one team underlined per match if assigned_teams has multiple (pick first).
    2. Excluded teams appear in italics but never assigned.
    3. Insert 'Lunch Break' or 'Overnight' row if needed.
    4. If a match is immediately after 'Lunch Break' or 'Overnight', set its gap to 'Lunch Break'/'Overnight' (and don't calculate minutes).
    5. Keep color styling for assigned teams.
    6. Title includes date/time and cache usage info.
    """

    member_schedule = []
    previous_assigned_match_time = None
    previous_assigned_match_index = None

    # We'll track whether the *last row* we inserted was a 'Lunch Break' or 'Overnight'
    last_break_inserted = None  # can be "Lunch Break", "Overnight", or None

    for i, match in enumerate(schedule):
        assigned_team_for_this_member = None
        for team in match["teams"]:
            if team in assigned_teams and team not in EXCLUDED_TEAMS:
                assigned_team_for_this_member = team
                break

        if assigned_team_for_this_member:
            match_time = datetime.strptime(match["time"], "%Y-%m-%dT%H:%M:%S")

            # Insert row for lunch break or overnight if needed
            if previous_assigned_match_time is not None:
                gap_minutes = (match_time - previous_assigned_match_time).total_seconds() / 60
                if match_time.date() != previous_assigned_match_time.date():
                    member_schedule.append({
                        "matchNumber": "Overnight",
                        "time": "",
                        "gap": "",
                        "teams": []
                    })
                    last_break_inserted = "Overnight"
                elif gap_minutes >= LUNCH_BREAK_THRESHOLD_MINUTES:
                    member_schedule.append({
                        "matchNumber": "Lunch Break",
                        "time": "",
                        "gap": "",
                        "teams": []
                    })
                    last_break_inserted = "Lunch Break"
                else:
                    last_break_inserted = None
            else:
                # If this is the first match assigned to the member, no gap
                last_break_inserted = None

            # Now compute the gap for THIS match
            gap = None
            if previous_assigned_match_time is not None:
                # If the preceding row was 'Lunch Break' or 'Overnight', just replicate that in gap
                if last_break_inserted in ["Lunch Break", "Overnight"]:
                    gap = last_break_inserted
                else:
                    # Normal gap calculation
                    if (
                        previous_assigned_match_index is not None and
                        match["matchNumber"] == schedule[previous_assigned_match_index]["matchNumber"] + 1
                    ):
                        gap = "N/A"
                    else:
                        gap_start = None
                        gap_end = match_time
                        if previous_assigned_match_index is not None and (previous_assigned_match_index + 1) < i:
                            gap_start_str = schedule[previous_assigned_match_index + 1]["time"]
                            gap_start = datetime.strptime(gap_start_str, "%Y-%m-%dT%H:%M:%S")
                        else:
                            gap_start = previous_assigned_match_time
                        if gap_start:
                            gap_diff = (gap_end - gap_start).total_seconds() / 60
                            if gap_diff > GAP_UNDERLINE_THRESHOLD_MINUTES:
                                gap = f"<span style='text-decoration: underline;'>{gap_diff:.0f} minutes</span>"
                            else:
                                gap = f"{gap_diff:.0f} minutes"
            # If there's no previous assigned match, it's first match -> "N/A" gap
            if gap is None:
                gap = "N/A"

            # Build styled team list
            styled_teams = []
            used_underline = False
            for t in match["teams"]:
                if t in EXCLUDED_TEAMS:
                    styled_teams.append(f"<i>Team {t} (Excluded)</i>")
                elif t == assigned_team_for_this_member and not used_underline:
                    styled_teams.append(
                        f"<span class='team team-{t}' style='text-decoration: underline;'>Team {t}</span>"
                    )
                    used_underline = True
                else:
                    styled_teams.append(f"<span class='team team-{t}'>Team {t}</span>")

            member_schedule.append({
                "matchNumber": match["matchNumber"],
                "time": match["time"],
                "gap": gap,
                "teams": styled_teams,
            })

            previous_assigned_match_time = match_time
            previous_assigned_match_index = i

    # Render HTML
    template = Template(r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{{ member }}'s Scouting Schedule - {{ generation_info }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 1in; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid black; padding: 8px; text-align: center; }
        th { background-color: #f2f2f2; }
        .team { padding: 5px; font-weight: bold; }
        .excluded { font-style: italic; }
        .break-row { font-weight: bold; background-color: #ffd700; }
        {% for t in assigned_teams %}
        .team-{{ t }} {
            background-color: hsl({{ loop.index0 * 60 }}, 70%, 90%);
            border: 1px solid black;
        }
        {% endfor %}
        @media print {
            .team {
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }
        }
    </style>
</head>
<body>
    <h1>{{ member }}'s Scouting Schedule</h1>
    <p><strong>Generated Info:</strong> {{ generation_info }}</p>
    <h2>Assigned Teams:</h2>
    <ul>
        {% for t in assigned_teams %}
        <li class="team team-{{ t }}">Team {{ t }}</li>
        {% endfor %}
    </ul>
    <table>
        <thead>
            <tr>
                <th>Match</th>
                <th>Time</th>
                <th>Gap</th>
                <th>Teams</th>
            </tr>
        </thead>
        <tbody>
            {% for match in member_schedule %}
            <tr class="{% if match.matchNumber in ['Lunch Break', 'Overnight'] %}break-row{% endif %}">
                <td>{{ match.matchNumber }}</td>
                <td>{{ match.time }}</td>
                <td>{{ match.gap|safe }}</td>
                <td>{{ match.teams|join(', ')|safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
""")

    return template.render(member=member, member_schedule=member_schedule, assigned_teams=assigned_teams, generation_info=generation_info)

def generate_overall_schedule(schedule, assignments, team_assignments, generation_info):
    annotated_schedule = []
    previous_match_time = None

    for match in schedule:
        match_time = datetime.strptime(match["time"], "%Y-%m-%dT%H:%M:%S")
        if previous_match_time:
            time_diff_minutes = (match_time - previous_match_time).total_seconds() / 60
            if time_diff_minutes >= LUNCH_BREAK_THRESHOLD_MINUTES:
                annotated_schedule.append({
                    "matchNumber": "Lunch Break",
                    "time": "",
                    "teams": [],
                    "assignedMembers": [],
                })
            elif match_time.date() != previous_match_time.date():
                annotated_schedule.append({
                    "matchNumber": "Overnight",
                    "time": "",
                    "teams": [],
                    "assignedMembers": [],
                })

        overall_assigned = []
        for team in match["teams"]:
            if team in team_assignments:
                overall_assigned.append(f"<u>Team {team}</u>: {', '.join(team_assignments[team])}")
            else:
                overall_assigned.append(f"<i>Team {team} (Excluded)</i>")

        annotated_schedule.append({
            "matchNumber": match["matchNumber"],
            "time": match["time"],
            "teams": match["teams"],
            "assignedMembers": overall_assigned,
        })
        previous_match_time = match_time

    template = Template(r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Overall Scouting Schedule - {{ generation_info }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 1in; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid black; padding: 8px; text-align: center; }
        th { background-color: #f2f2f2; }
        .break { font-weight: bold; background-color: #ffd700; }
    </style>
</head>
<body>
    <h1>Overall Scouting Schedule</h1>
    <p><strong>Generated Info:</strong> {{ generation_info }}</p>
    <table>
        <thead>
            <tr>
                <th>Match</th>
                <th>Time</th>
                <th>Teams</th>
                <th>Assigned Members</th>
            </tr>
        </thead>
        <tbody>
            {% for match in annotated_schedule %}
            <tr class="{% if match.matchNumber in ['Lunch Break', 'Overnight'] %}break{% endif %}">
                <td>{{ match.matchNumber }}</td>
                <td>{{ match.time }}</td>
                <td>{{ match.teams|join(', ') }}</td>
                <td>{{ match.assignedMembers|join('<br>')|safe }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h1>Team Assignments</h1>
    <table>
        <thead>
            <tr>
                <th>Member</th>
                <th>Assigned Teams</th>
            </tr>
        </thead>
        <tbody>
            {% for member, teams in assignments.items() %}
            <tr>
                <td>{{ member }}</td>
                <td>{{ teams|join(', ') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
""")

    return template.render(annotated_schedule=annotated_schedule, assignments=assignments, generation_info=generation_info)


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    use_cache = input("Use cached data? (yes/no): ").strip().lower() == "yes"
    if use_cache:
        data = load_cache()
        if data:
            mtime = os.path.getmtime(CACHE_FILE)
            cache_time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            generation_info = f"Used cache from {cache_time_str}, generated at {now_str}"
        else:
            print("No cache found. Fetching data from API.")
            data = fetch_schedule()
            save_cache(data)
            generation_info = f"No valid cache. Fresh fetch at {now_str}"
    else:
        data = fetch_schedule()
        save_cache(data)
        generation_info = f"Fetched new data at {now_str}"

    schedule = [
        {
            "matchNumber": match["matchNumber"],
            "time": match["startTime"],
            # Convert to int
            "teams": [int(team["teamNumber"]) for team in match["teams"]]
        }
        for match in data["Schedule"]
        if match["tournamentLevel"] == TOURNAMENT_LEVEL.capitalize()
    ]
    print("DEBUG: Schedule processed from API\n", schedule, "\n")

    assignments, team_assignments = assign_scouting(
        schedule, SCOUTING_MEMBERS, MIN_TEAMS_PER_MEMBER, MIN_MEMBERS_PER_TEAM
    )

    overall_html = generate_overall_schedule(schedule, assignments, team_assignments, generation_info)
    with open("overall_schedule.html", "w") as f:
        f.write(overall_html)
    print(f"Generated overall schedule: overall_schedule.html")

    for member in SCOUTING_MEMBERS:
        member_schedule_html = generate_member_schedule(member, schedule, team_assignments, assignments[member], generation_info)
        file_name = f"{member.replace(' ', '_').lower()}_schedule.html"
        with open(file_name, "w") as f:
            f.write(member_schedule_html)
        print(f"Generated schedule for {member}: {file_name}")


if __name__ == "__main__":
    main()
