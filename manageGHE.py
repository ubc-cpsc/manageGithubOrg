#!/usr/bin/env -S python3 -i

import os
import logging
import requests


class manageGHE:

    logger = None
    apiURL = 'https://github.students.cs.ubc.ca/api/v3'
    org = None
    token = None
    github_headers = { 'Accept': 'application/vnd.github.v3+json' }

    def __init__(self, logger=None, verbose=False):
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger('manageGHE')
            self.logger.setLevel(logging.DEBUG)

            # dump to standard out
            from sys import stdout
            ch = logging.StreamHandler(stdout)
            ch.setLevel(logging.INFO)
            if verbose:
                ch.setLevel(logging.DEBUG)
            # Prefix with context 
            formatter = logging.Formatter('[%(asctime)s] %(process)d %(levelname)s %(message)s', datefmt='%d/%b/%Y %H:%M:%S')
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

        self.apiURL = os.getenv('GHE_APIURL', self.apiURL)
        self.org = os.getenv('GHE_ORG', self.org)
        self.setToken(os.getenv('GHE_TOKEN', self.token))
        if not self.org:
            self.logger.warning("GHE Org not set. (Use GHE_ORG environment variable.)")
        if not self.token:
            self.logger.warning("GHE Token not set. (Use GHE_TOKEN environment variable.)")

    def _getSession(self):
        if not self.token:
            self.logger.error("Must set token first")
            return None
        if not self.org:
            self.logger.error("Must set org first")
            return None
        mySession = requests.Session()
        mySession.headers.update(self.github_headers)
        return mySession

    def setToken(self, token):
        self.token = token
        if token:
            self.github_headers['Authorization'] = 'token ' + self.token
        else:
            del self.github_headers['Authorization']

    def getTeamMembership(self, team):
        """ Grab current github user list, return a dictionary of users {uid: {'uid': uid, 'puid': None, 'stud_no': None, 'emp_no': None}} """

        with self._getSession() as s:

            myURL = f"{self.apiURL}/orgs/{self.org}/teams/{team}/members?since"
            users = {}
            while True:
                r = s.get(myURL)
                if r.status_code == 200:
                    for item in r.json():
                        if item['type'] == 'User':
                            users[item['login']] = item

                    # https://docs.github.com/en/enterprise-server@2.21/rest/guides/traversing-with-pagination
                    if 'Link' in r.headers:
                        links = { x.split(';')[1].strip() : x.split(';')[0].strip(' <>') for x in r.headers['Link'].split(',') }
                    else:
                        links = {}
                    if 'rel="next"' in links:
                        myURL = links['rel="next"']
                    else:
                        return list(users.keys())
                else:
                    self.logger.error("grabUsersFromGHE status code %s", r.status_code)
                    return None



    def createAssnRepos(self, assn, users, template=None, userPerms='pull'):
        """ Create assignment {assn} for list {users}, optionally using repo {template}.
        Default permissions set to read for staff and write for user. """

        # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#add-a-repository-collaborator
        if userPerms not in {'pull', 'push', 'admin'}:
            self.logger.error("Invalid userPerms")
            return

        if not isinstance(users, list):
            self.logger.error("users needs to be a list")
            return

        allRepos = { f"{assn}_{user}" : user for user in users }

        with self._getSession() as s:
            # Grab the 'staff' team id for setting permissions later.
            myURL = f"{self.apiURL}/orgs/{self.org}/teams/staff"
            r = s.get(myURL)
            if r.status_code != 200:
                self.logger.error("Required 'staff' team was not found in the %s organization. Please create manually.", self.org)
                return
            staff_team_id = r.json()['id']

            if template:
                r = s.get(f"{self.apiURL}/repos/{template}", headers={'Accept': 'application/vnd.github.baptiste-preview+json'})
                if r.status_code != 200:
                    self.logger.error("template %s is not a repo. Status code = %s. Should be of the form 'owner/repo'", template, r.status_code)
                    return
                if not r.json()['is_template']:
                    self.logger.error("%s is not a 'template' repo.", template)
                    return

            # Lookup all current repos
            myURL = f"{self.apiURL}/orgs/{self.org}/repos"
            repos = {}
            while True:
                r = s.get(myURL)
                if r.status_code == 200:
                    for item in r.json():
                        if item['name'].startswith(f"{assn}_"):
                            repos[item['name']] = item

                    # https://docs.github.com/en/enterprise-server@2.21/rest/guides/traversing-with-pagination
                    if 'Link' in r.headers:
                        links = { x.split(';')[1].strip() : x.split(';')[0].strip(' <>') for x in r.headers['Link'].split(',') }
                    else:
                        links = {}
                    if 'rel="next"' in links:
                        myURL = links['rel="next"']
                    else:
                        break
                else:
                    self.logger.error("GHE API status code %s", r.status_code)
                    return None

            # These are the missing repos to create
            reposToCreate = allRepos.keys() - repos.keys()

            for repo in reposToCreate:
                # Create a repo.
                # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#create-an-organization-repository
                myURL = f"{self.apiURL}/orgs/{self.org}/repos"
                myTemplateURL = f"{self.apiURL}/repos/{template}/generate"
                payload = {
                    'name': repo,
                    'team_id': staff_team_id,
                    'private': True,
                    'owner': self.org,
                }
                self.logger.info("creating repo: %s", repo)
                if template:
                    # The template API doesn't support setting the team.
                    del payload['team_id']
                    r = s.post(myTemplateURL, json=payload, headers={'Accept': 'application/vnd.github.baptiste-preview+json'})
                else:
                    r = s.post(myURL, json=payload)
                if r.status_code == 201:
                    self.logger.debug("created repo %s", repo)
                else:
                    raise AssertionError(f"createRepo should not fail. {r.status_code}")

                # Set permissions on (add collaborators to) the newly created repo.
                repoURL = r.json()['url']
                payload = { 'permission' : userPerms }
                myURL = f"{repoURL}/collaborators/{allRepos[repo]}"
                r = s.put(myURL, json=payload)
                if r.status_code == 201:
                    self.logger.info("Permissions: %s@%s set to %s. (Invitation sent)", allRepos[repo], repo, userPerms)
                elif r.status_code == 204:
                    # The docs say 204 is "when person is already a collaborator", but that doesn't seems to be entirely true.
                    # Seems you get this message if permissions are simply set and no invitation sent.
                    self.logger.info("Permissions: %s@%s set to %s.", allRepos[repo], repo, userPerms)
                else:
                    raise AssertionError("change repo permissions should not fail")




    def setAssnPerms(self, assn, userPerms='pull', staffPerms='pull'):
        """ Query perms for all assignment {assn} and update perms. """

        # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#add-a-repository-collaborator
        if userPerms not in {'pull', 'push', 'admin'}:
            self.logger.error("Invalid userPerms")
            return
        userPermsD = {
            "admin": True if userPerms == 'admin' else False,
            "push": True if userPerms in ['admin', 'push'] else False,
            "pull": True,
        }
        userPermsPayload = {'permission': userPerms }
        if staffPerms not in {'pull', 'push', 'admin'}:
            self.logger.error("Invalid staffPerms")
            return
        staffPermsD = {
            "admin": True if staffPerms == 'admin' else False,
            "maintain": False,
            "push": True if staffPerms in ['admin', 'push'] else False,
            "triage": False,
            "pull": True,
        }
        staffPermsPayload = {'permission': staffPerms }

        with self._getSession() as s:
            # Grab the 'staff' team id for setting permissions later.
            myURL = f"{self.apiURL}/orgs/{self.org}/teams/staff"
            r = s.get(myURL)
            if r.status_code != 200:
                self.logger.error("Required 'staff' team was not found in the %s organization. Please create manually.", self.org)
                return
            staff_team_repos = r.json()['repositories_url']

            # Lookup all current repos
            myURL = f"{self.apiURL}/orgs/{self.org}/repos"
            repos = {}
            while True:
                r = s.get(myURL)
                if r.status_code == 200:
                    for item in r.json():
                        if item['name'].startswith(f"{assn}_"):
                            repos[item['name']] = item

                    # https://docs.github.com/en/enterprise-server@2.21/rest/guides/traversing-with-pagination
                    if 'Link' in r.headers:
                        links = { x.split(';')[1].strip() : x.split(';')[0].strip(' <>') for x in r.headers['Link'].split(',') }
                    else:
                        links = {}
                    if 'rel="next"' in links:
                        myURL = links['rel="next"']
                    else:
                        break
                else:
                    self.logger.error("GHE API status code %s", r.status_code)
                    return None

            # Do all the direct collaborators (students) first, and then the staff team.
            for v in repos.values():
                owner_name = v['full_name']
                # Grab the list of direct collaborators
                # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#list-repository-collaborators
                u_collab = f"{self.apiURL}/repos/{owner_name}/collaborators"
                r = s.get(f"{u_collab}?affiliation=direct")
                if r.status_code == 200:
                    for item in r.json():
                        if item['permissions'] != userPermsD:
                            self.logger.info("Permissions: %s@%s set to %s. Was %s", item['login'], owner_name, userPerms, item['permissions'])
                            fix = s.put(f"{u_collab}/{item['login']}", json=userPermsPayload)
                            if fix.status_code != 204:
                                self.logger.error("GHE API set user perms status code %s", fix.status_code)
                                return None
                else:
                    self.logger.error("GHE API status code %s", r.status_code)
                    return None

            for v in repos.values():
                owner_name = v['full_name']
                # Look up the staff team permissions on the repo.
                # https://docs.github.com/en/enterprise-server@2.21/rest/reference/teams#check-team-permissions-for-a-repository
                u_teams = f"{staff_team_repos}/{owner_name}"
                r = s.get(u_teams, headers={'Accept': 'application/vnd.github.v3.repository+json'})
                if r.status_code == 200:
                    existingStaffPermsD = r.json()['permissions']
                elif r.status_code == 404:
                    existingStaffPermsD = None
                else:
                    self.logger.error(f"%s returned %s", u_teams, r.status_code)
                    return None
                if existingStaffPermsD != staffPermsD:
                    self.logger.info("Permissions: staff(team)@%s set to %s. Was %s", owner_name, staffPerms, existingStaffPermsD)
                    fix = s.put(u_teams, json=staffPermsPayload)
                    if fix.status_code != 204:
                        self.logger.error("GHE API set staff perms status code %s", fix.status_code)
                        return None

    def __repr__(self):
        retVal = ""
        retVal += f"API URL: {self.apiURL}\n"
        retVal += f"    Org: {self.org}\n"
        retVal += f"Headers: {self.github_headers}\n"
        return retVal

if __name__ == "__main__":
    m=manageGHE()
    print("m=manageGHE()")
    print(m)