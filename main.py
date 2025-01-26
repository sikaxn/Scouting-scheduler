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
TOURNAMENT_LEVEL = "practice"  # Options: "practice" or "qualification"
CACHE_FILE = "schedule_cache.json"
SCOUTING_MEMBERS = [
    "Alex Carter", "Jordan Smith", "Taylor Johnson", "Morgan Davis", "Casey Brown",
    "Riley Wilson", "Jamie Anderson", "Drew Thompson", "Peyton Martinez", "Quinn Moore",
    "Cameron Taylor", "Reese Clark", "Logan Lewis", "Avery Lee", "Charlie Hall"
]


MIN_TEAMS_PER_MEMBER = 4
MIN_MEMBERS_PER_TEAM = 2
LUNCH_BREAK_THRESHOLD_MINUTES = 60  # Minutes to detect lunch breaks
GAP_UNDERLINE_THRESHOLD_MINUTES = 15  # Minimum gap (in minutes) for underline styling

# Fetch match schedule from the API
def fetch_schedule():
    url = f"https://frc-api.firstinspires.org/v3.0/{SEASON}/schedule/{EVENT_CODE}?tournamentLevel={TOURNAMENT_LEVEL}"
    response = requests.get(url, auth=(API_USERNAME, API_PASSWORD))
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch schedule: {response.status_code} {response.reason}")

# Save schedule to cache
def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)

# Load cached schedule
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return None

# Assign scouting members to teams
def assign_scouting(schedule, members, min_teams, min_members):
    assignments = {member: [] for member in members}
    team_assignments = {team: [] for match in schedule for team in match["teams"]}
    members_cycle = cycle(members)

    # Assign each team to at least min_members members
    for team in team_assignments:
        while len(team_assignments[team]) < min_members:
            member = next(members_cycle)
            if team not in assignments[member]:
                assignments[member].append(team)
                team_assignments[team].append(member)

    # Ensure each member has at least min_teams
    teams_cycle = cycle(team_assignments.keys())
    for member in assignments:
        while len(assignments[member]) < min_teams:
            team = next(teams_cycle)
            if member not in team_assignments[team]:
                assignments[member].append(team)
                team_assignments[team].append(member)

    return assignments, team_assignments

# Generate an individual member's schedule
def generate_member_schedule(member, schedule, team_assignments, assigned_teams):
    member_schedule = []
    previous_assigned_match_time = None
    previous_assigned_match_index = None

    for i, match in enumerate(schedule):
        # Check if the member is assigned to any team in this match
        teams_scouted_by_member = [team for team in match["teams"] if team in assigned_teams]
        if teams_scouted_by_member:
            match_time = datetime.strptime(match["time"], '%Y-%m-%dT%H:%M:%S')
            gap = None

            if previous_assigned_match_time is not None:
                # Handle continuous match numbers
                if match["matchNumber"] == schedule[previous_assigned_match_index]["matchNumber"] + 1:
                    gap = "N/A"
                else:
                    # Calculate the gap for skipped matches
                    gap_start = None
                    gap_end = match_time

                    # Use the start time of skipped matches to determine the gap
                    skipped_matches = schedule[previous_assigned_match_index + 1:i]
                    if skipped_matches:
                        # First skipped match start time = gap start
                        gap_start = datetime.strptime(skipped_matches[0]["time"], '%Y-%m-%dT%H:%M:%S')
                        # Last skipped match end time = start time of the next match
                        gap_end = match_time
                    else:
                        # No skipped matches, use previous match's start time
                        gap_start = previous_assigned_match_time

                    # Calculate time difference in minutes
                    time_diff_minutes = (gap_end - gap_start).total_seconds() / 60

                    # Classify the gap
                    if match_time.date() != previous_assigned_match_time.date():
                        gap = "<span style='text-decoration: underline;'>Overnight</span>"
                    elif time_diff_minutes >= LUNCH_BREAK_THRESHOLD_MINUTES:
                        gap = "<span style='text-decoration: underline;'>Lunch Break</span>"
                    elif time_diff_minutes > GAP_UNDERLINE_THRESHOLD_MINUTES:
                        gap = f"<span style='text-decoration: underline;'>{time_diff_minutes:.0f} minutes</span>"
                    elif time_diff_minutes == 0:
                        gap = "N/A"
                    else:
                        gap = f"{time_diff_minutes:.0f} minutes"  # No underline for small gaps

            # Add match details to the member's schedule
            member_schedule.append({
                "matchNumber": match["matchNumber"],
                "time": match["time"],
                "gap": gap or "N/A",
                "teams": match["teams"]
            })

            # Update the previous match details
            previous_assigned_match_time = match_time
            previous_assigned_match_index = i

    # Render the schedule into HTML
    template = Template("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{{ member }}'s Scouting Schedule</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 1in; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid black; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .team { padding: 5px; color: black; font-weight: bold; }
            {% for team in assigned_teams %}
            .team-{{ team }} { background-color: hsl({{ loop.index0 * 60 }}, 70%, 90%); border: 1px solid black; }
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
        <h2>Assigned Teams:</h2>
        <ul>
            {% for team in assigned_teams %}
            <li class="team team-{{ team }}">Team {{ team }}</li>
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
                <tr>
                    <td>{{ match.matchNumber }}</td>
                    <td>{{ match.time }}</td>
                    <td>{{ match.gap|safe }}</td>
                    <td>
                        {% for team in match.teams %}
                        <span class="team team-{{ team }}">Team {{ team }}</span>
                        {% endfor %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </body>
    </html>
    """)
    return template.render(member=member, member_schedule=member_schedule, assigned_teams=assigned_teams)

def generate_overall_schedule(schedule, assignments, team_assignments):
    annotated_schedule = []
    previous_match_time = None

    # Annotate the schedule with breaks
    for match in schedule:
        match_time = datetime.strptime(match["time"], '%Y-%m-%dT%H:%M:%S')
        if previous_match_time:
            time_diff_minutes = (match_time - previous_match_time).total_seconds() / 60
            if time_diff_minutes >= LUNCH_BREAK_THRESHOLD_MINUTES:
                annotated_schedule.append({
                    "matchNumber": "Lunch Break",
                    "time": "",
                    "teams": [],
                    "assignedMembers": []
                })
            elif match_time.date() != previous_match_time.date():
                annotated_schedule.append({
                    "matchNumber": "Overnight",
                    "time": "",
                    "teams": [],
                    "assignedMembers": []
                })

        annotated_schedule.append({
            "matchNumber": match["matchNumber"],
            "time": match["time"],
            "teams": match["teams"],
            "assignedMembers": [
                f"Team {team}: {', '.join(team_assignments[team])}" for team in match["teams"]
            ]
        })
        previous_match_time = match_time

    # Render the schedule and assignments into HTML
    template = Template("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Overall Scouting Schedule</title>
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
                    <td>{{ match.assignedMembers|join('<br>') }}</td>
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
    return template.render(annotated_schedule=annotated_schedule, assignments=assignments)


def main():
    use_cache = input("Use cached data? (yes/no): ").strip().lower() == "yes"
    if use_cache:
        data = load_cache()
        if not data:
            print("No cache found. Fetching data from API.")
            data = fetch_schedule()
            save_cache(data)
    else:
        data = fetch_schedule()
        save_cache(data)

    schedule = [
        {
            "matchNumber": match["matchNumber"],
            "time": match["startTime"],
            "teams": [team["teamNumber"] for team in match["teams"]]
        } for match in data["Schedule"] if match["tournamentLevel"] == TOURNAMENT_LEVEL.capitalize()
    ]

    assignments, team_assignments = assign_scouting(schedule, SCOUTING_MEMBERS, MIN_TEAMS_PER_MEMBER, MIN_MEMBERS_PER_TEAM)

    # Generate overall schedule
    overall_html = generate_overall_schedule(schedule, assignments, team_assignments)
    with open("overall_schedule.html", "w") as f:
        f.write(overall_html)
    print("Generated overall schedule: overall_schedule.html")

    # Generate individual schedules for each member
    for member in SCOUTING_MEMBERS:
        member_schedule_html = generate_member_schedule(member, schedule, team_assignments, assignments[member])
        file_name = f"{member.replace(' ', '_').lower()}_schedule.html"
        with open(file_name, "w") as f:
            f.write(member_schedule_html)
        print(f"Generated schedule for {member}: {file_name}")


if __name__ == "__main__":
    main()
