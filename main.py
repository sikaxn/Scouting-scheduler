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

def insert_all_teams_done(schedule):
    """
    Insert a single 'AllTeamsDone' row after the match in which
    all teams (excluded included) have appeared at least once.
    """
    # Gather all possible teams (excluded or not)
    all_teams = set()
    for row in schedule:
        if row["matchNumber"] not in ["Lunch Break", "Overnight", "AllTeamsDone"]:
            all_teams.update(row["teams"])

    encountered = set()
    new_sched = []
    inserted = False

    # Sort by time for chronological insertion
    s_sorted = sorted(schedule, key=lambda m: m["time"])

    for row in s_sorted:
        new_sched.append(row)
        if row["matchNumber"] not in ["Lunch Break", "Overnight", "AllTeamsDone"]:
            encountered.update(row["teams"])
            if (not inserted) and (encountered == all_teams):
                # Insert the special row
                new_sched.append({
                    "matchNumber": "AllTeamsDone",
                    "time": "",
                    "teams": []
                })
                inserted = True

    return new_sched

def assign_scouting(schedule, members, min_teams, min_members):
    """
    1) Ignore 'Lunch Break', 'Overnight', 'AllTeamsDone' rows.
    2) For other matches, gather non-excluded teams in 'team_assignments'.
    3) Assign each team to members until min_members coverage, then ensure each member meets min_teams coverage.
    4) Purge excluded if it slipped in.
    """
    print("DEBUG: Building assignments for non-excluded teams...")
    assignments = {m: [] for m in members}
    team_assignments = {}

    for row in schedule:
        if row["matchNumber"] not in ["Lunch Break", "Overnight", "AllTeamsDone"]:
            for team in row["teams"]:
                if team not in EXCLUDED_TEAMS:
                    if team not in team_assignments:
                        team_assignments[team] = []

    print(f"DEBUG: Found {len(team_assignments)} non-excluded teams: {list(team_assignments.keys())}\n")

    members_cycle = cycle(members)
    # min_members coverage
    for team in team_assignments:
        while len(team_assignments[team]) < min_members:
            mem = next(members_cycle)
            if team not in assignments[mem]:
                assignments[mem].append(team)
                team_assignments[team].append(mem)
        print(f"DEBUG: Team {team} => {team_assignments[team]}")

    print("\nDEBUG: After ensuring min_members, assignments dictionary:")
    for m in assignments:
        print(f"  {m}: {assignments[m]}")

    # min_teams coverage
    teams_cycle = cycle(team_assignments.keys())
    for mem in assignments:
        while len(assignments[mem]) < min_teams:
            t = next(teams_cycle)
            if t not in assignments[mem]:
                assignments[mem].append(t)
                team_assignments[t].append(mem)

    print("\nDEBUG: After ensuring min_teams, assignments dictionary (pre-purge):")
    for m in assignments:
        print(f"  {m}: {assignments[m]}")

    # Purge excluded
    for m in assignments:
        orig_count = len(assignments[m])
        assignments[m] = [t for t in assignments[m] if t not in EXCLUDED_TEAMS]
        if len(assignments[m]) < orig_count:
            print(f"DEBUG: Purged excluded from {m}. => {assignments[m]}")

    print("\nDEBUG: Final assignment dictionary (post-purge):")
    for m in assignments:
        print(f"  {m}: {assignments[m]}")

    return assignments, team_assignments

def generate_overall_schedule(schedule, assignments, team_assignments, generation_info):
    """
    Insert 'Overnight' if date changes => priority,
    else if big gap => 'Lunch Break'.
    Also handle 'AllTeamsDone' row with a separate color.
    """
    annotated_schedule = []
    previous_match_time = None

    for row in schedule:
        if row["matchNumber"] == "AllTeamsDone":
            # new color row, after all teams have played
            annotated_schedule.append({
                "matchNumber": "AllTeamsDone",
                "time": "",
                "teams": [],
                "assignedMembers": []
            })
            continue

        # normal match row
        match_time = datetime.strptime(row["time"], "%Y-%m-%dT%H:%M:%S")
        if previous_match_time:
            if match_time.date() != previous_match_time.date():
                # priority overnight
                annotated_schedule.append({
                    "matchNumber": "Overnight",
                    "time": "",
                    "teams": [],
                    "assignedMembers": []
                })
            else:
                # big gap => lunch
                gap_min = (match_time - previous_match_time).total_seconds() / 60
                if gap_min >= LUNCH_BREAK_THRESHOLD_MINUTES:
                    annotated_schedule.append({
                        "matchNumber": "Lunch Break",
                        "time": "",
                        "teams": [],
                        "assignedMembers": []
                    })

        overall_assigned = []
        for t in row["teams"]:
            if t in team_assignments:
                overall_assigned.append(f"<u>Team {t}</u>: {', '.join(team_assignments[t])}")
            else:
                overall_assigned.append(f"<i>Team {t} (Excluded)</i>")

        annotated_schedule.append({
            "matchNumber": row["matchNumber"],
            "time": row["time"],
            "teams": row["teams"],
            "assignedMembers": overall_assigned,
        })

        previous_match_time = match_time

    # Render
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
        .allteamsdone { font-weight: bold; background-color: #90ee90; }
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
            {% for row in annotated_schedule %}
            {% set row_class = '' %}
            {% if row.matchNumber in ['Lunch Break', 'Overnight'] %}
                {% set row_class = 'break' %}
            {% elif row.matchNumber == 'AllTeamsDone' %}
                {% set row_class = 'allteamsdone' %}
            {% endif %}

            <tr class=\"{{ row_class }}\">
                <td>{{ row.matchNumber }}</td>
                <td>{{ row.time }}</td>
                <td>{{ row.teams|join(', ') }}</td>
                <td>{{ row.assignedMembers|join('<br>')|safe }}</td>
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
            {% for mem, teams in assignments.items() %}
            <tr>
                <td>{{ mem }}</td>
                <td>{{ teams|join(', ') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
""")
    return template.render(annotated_schedule=annotated_schedule, generation_info=generation_info, assignments=assignments)


def generate_member_schedule(member, schedule, team_assignments, assigned_teams, generation_info, full_assignments):
    """
    1) Skip break rows from schedule. We'll insert them ourselves if needed.
    2) If match is assigned to this member => show it. Else skip.
    3) Priority overnight vs. lunch break in date/gap logic.
    4) If 'AllTeamsDone' => skip or handle as you prefer. Here we skip for member's schedule.
    5) If last break inserted was 'Overnight' or 'Lunch Break', the next match's gap = that label (not minutes).
    """

    member_schedule = []
    previous_assigned_match_time = None
    previous_assigned_match_index = None
    last_break_inserted = None

    # Build (team -> other members) structure for top "Assigned Teams"
    assigned_teams_info = []
    for t in assigned_teams:
        also_members = []
        for other_m, tlist in full_assignments.items():
            if other_m != member and t in tlist:
                also_members.append(other_m)
        if also_members:
            assigned_teams_info.append((t, ", ".join(also_members)))
        else:
            assigned_teams_info.append((t, ""))

    # Sort the schedule by time if not already
    schedule_sorted = sorted(schedule, key=lambda r: r["time"])

    for i, row in enumerate(schedule_sorted):
        # If it's a break row => skip
        if row["matchNumber"] in ["Lunch Break", "Overnight", "AllTeamsDone"]:
            continue

        assigned_team_for_this_member = None
        for tm in row["teams"]:
            if tm in assigned_teams and tm not in EXCLUDED_TEAMS:
                assigned_team_for_this_member = tm
                break

        if assigned_team_for_this_member:
            match_time = datetime.strptime(row["time"], "%Y-%m-%dT%H:%M:%S")

            # Insert lunch/overnight logic
            if previous_assigned_match_time is not None:
                gap_minutes = (match_time - previous_assigned_match_time).total_seconds() / 60
                # Priority => date shift => overnight
                if match_time.date() != previous_assigned_match_time.date():
                    member_schedule.append({
                        "matchNumber": "Overnight",
                        "time": "",
                        "gap": "",
                        "teams": []
                    })
                    last_break_inserted = "Overnight"
                else:
                    if gap_minutes >= LUNCH_BREAK_THRESHOLD_MINUTES:
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
                last_break_inserted = None

            # compute gap for this match
            if last_break_inserted in ["Overnight", "Lunch Break"]:
                gap = last_break_inserted
            else:
                gap = None
                if previous_assigned_match_time is not None:
                    # find next real match row after 'previous_assigned_match_index'
                    # skip any break rows in between
                    found_gap_start = previous_assigned_match_time
                    if previous_assigned_match_index is not None:
                        for skip_i in range(previous_assigned_match_index + 1, len(schedule_sorted)):
                            if schedule_sorted[skip_i]["matchNumber"] not in ["Lunch Break","Overnight","AllTeamsDone"]:
                                found_gap_start = datetime.strptime(schedule_sorted[skip_i]["time"], "%Y-%m-%dT%H:%M:%S")
                                break

                    diff = (match_time - found_gap_start).total_seconds() / 60
                    if diff > GAP_UNDERLINE_THRESHOLD_MINUTES:
                        gap = f"<span style='text-decoration: underline;'>{diff:.0f} minutes</span>"
                    else:
                        gap = f"{diff:.0f} minutes"

            if gap is None:
                gap = "N/A"

            used_underline = False
            styled_teams = []
            for t in row["teams"]:
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
                "matchNumber": row["matchNumber"],
                "time": row["time"],
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
        {% for (tt,others) in assigned_teams_info %}
        .team-{{ tt }} {
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
    {% for (tm,other_mems) in assigned_teams_info %}
        <li class="team team-{{ tm }}">
            Team {{ tm }}
            {% if other_mems %}
               <em>(also assigned to: {{ other_mems }})</em>
            {% endif %}
        </li>
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
    return template.render(
        member=member,
        member_schedule=member_schedule,
        assigned_teams_info=assigned_teams_info,
        generation_info=generation_info
    )

def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    use_cache = input("Use cached data? (yes/no): ").strip().lower() == "yes"
    if use_cache:
        data = load_cache()
        if data:
            mtime = os.path.getmtime(CACHE_FILE)
            cache_time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            generation_info = (
                f"Used cache from {cache_time_str}, generated at {now_str}, "
                f"event: {EVENT_CODE}, year: {SEASON}"
            )
        else:
            print("No cache found. Fetching data from API.")
            data = fetch_schedule()
            save_cache(data)
            generation_info = (
                f"No valid cache. Fresh fetch at {now_str}, "
                f"event: {EVENT_CODE}, year: {SEASON}"
            )
    else:
        data = fetch_schedule()
        save_cache(data)
        generation_info = (
            f"Fetched new data at {now_str}, "
            f"event: {EVENT_CODE}, year: {SEASON}"
        )

    # Build raw schedule
    raw_schedule = [
        {
            "matchNumber": match["matchNumber"],
            "time": match["startTime"],
            "teams": [int(t["teamNumber"]) for t in match["teams"]]
        }
        for match in data["Schedule"]
        if match["tournamentLevel"] == TOURNAMENT_LEVEL.capitalize()
    ]
    print("DEBUG: Raw schedule from API:\n", raw_schedule, "\n")

    # Insert AllTeamsDone after the match that included all teams
    schedule_with_all = insert_all_teams_done(raw_schedule)

    # Do assignment
    assignments, team_assignments = assign_scouting(
        schedule_with_all,
        SCOUTING_MEMBERS,
        MIN_TEAMS_PER_MEMBER,
        MIN_MEMBERS_PER_TEAM
    )

    # overall schedule
    overall_html = generate_overall_schedule(schedule_with_all, assignments, team_assignments, generation_info)
    # rename overall file
    overall_filename = f"overall_schedule_{EVENT_CODE}_{SEASON}.html"
    with open(overall_filename, "w") as f:
        f.write(overall_html)
    print(f"Generated overall schedule: {overall_filename}")

    # generate each individual's schedule
    for member in SCOUTING_MEMBERS:
        member_schedule_html = generate_member_schedule(
            member=member,
            schedule=schedule_with_all,
            team_assignments=team_assignments,
            assigned_teams=assignments[member],
            generation_info=generation_info,
            full_assignments=assignments
        )
        safe_name = member.replace(' ', '_')
        file_name = f"individual_{safe_name}_{EVENT_CODE}_{SEASON}_schedule.html"
        with open(file_name, "w") as f:
            f.write(member_schedule_html)
        print(f"Generated schedule for {member}: {file_name}")


if __name__ == "__main__":
    main()
