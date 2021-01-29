#!/usr/bin/python3 -i

import os, sys
import logging
import requests


class manageGHE:

    logger = None
    apiURL = 'https://github.students.cs.ubc.ca/api/v3'
    org = None
    _token = None
    github_headers = { 'Accept': 'application/vnd.github.v3+json' }
    doUpdates = True

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
        self._token = os.getenv('GHE_TOKEN', self._token)
        if self._token:
            self.github_headers['Authorization'] = 'token ' + self._token
        self.doUpdates = False if os.getenv('GHE_DRYRUN') else True

    def _getSession(self):
        if not self._token:
            self.logger.error("Authorization token must be set first. ' export GHE_TOKEN=yourtokengoeshere' is recommended.")
            return None
        if not self.org:
            self.logger.error("Github org must be set first. 'export GHE_ORG=CPSCNNN_YYYYS-TN' is recommended.")
            return None
        mySession = requests.Session()
        mySession.headers.update(self.github_headers)
        return mySession

    def getTeamMembership(self, team):
        """ Grab the current list of users of a team in your org. """

        with self._getSession() as s:

            myURL = f"{self.apiURL}/orgs/{self.org}/teams/{team}/members"
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
                    self.logger.error("%s status_code: %s", myURL, r.status_code)
                    return None



    def createAssnRepos(self, assn, users, template=None, userPerms='pull'):
        """ Create assignment {assn} for list {users}, optionally using repo {template}.
        Default permissions set to read for staff and user. """

        if not self.doUpdates:
            self.logger.warning("DRY RUN - NO CHANGES WILL BE MADE")

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
                    self.logger.error("template %s is not a repo. Status code = %s. Should be of the form 'owner/repo'",
                                      template, r.status_code)
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
                    self.logger.error("%s status_code %s", myURL, r.status_code)
                    return None

            # These are the missing repos to create
            reposToCreate = allRepos.keys() - repos.keys()

            for repo in reposToCreate:
                # Create a repo.
                self.logger.info("creating repo: %s", repo)
                if self.doUpdates:
                    # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#create-an-organization-repository
                    myURL = f"{self.apiURL}/orgs/{self.org}/repos"
                    payload = {
                        'name': repo,
                        'team_id': staff_team_id,
                        'private': True,
                        'owner': self.org,
                    }
                    if template:
                        # The template API doesn't support setting the team.
                        del payload['team_id']
                        myURL = f"{self.apiURL}/repos/{template}/generate"
                        r = s.post(myURL, json=payload, headers={'Accept': 'application/vnd.github.baptiste-preview+json'})
                    else:
                        r = s.post(myURL, json=payload)
                    if r.status_code == 201:
                        self.logger.debug("created repo %s", repo)
                    else:
                        self.logger.critical("%s status_code %s", myURL, r.status_code)
                        return None

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
                        self.logger.critical("%s status_code %s", myURL, r.status_code)
                        return None




    def setAssnPerms(self, assn, userPerms=None, staffPerms=None, adminPerms=None):
        """ Query perms for all assignment {assn} and update perms. """

        if not self.doUpdates:
            self.logger.warning("DRY RUN - NO CHANGES WILL BE MADE")

        # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#add-a-repository-collaborator
        if userPerms:
            if userPerms not in {'pull', 'push', 'admin'}:
                self.logger.error("Invalid userPerms")
                return
            userPermsPayload = { 'permission': userPerms }
            userPermsD = {
                "admin": True if userPerms == 'admin' else False,
                "push": True if userPerms in ['admin', 'push'] else False,
                "pull": True,
            }
        if staffPerms:
            if staffPerms not in {'pull', 'push', 'admin'}:
                self.logger.error("Invalid staffPerms")
                return
            staffPermsPayload = { 'permission': staffPerms }
            staffPermsD = {
                "admin": True if staffPerms == 'admin' else False,
                "maintain": False,
                "push": True if staffPerms in ['admin', 'push'] else False,
                "triage": False,
                "pull": True,
            }
        if adminPerms:
            if adminPerms not in {'pull', 'push', 'admin'}:
                self.logger.error("Invalid adminPerms")
                return
            adminPermsPayload = { 'permission': adminPerms }
            adminPermsD = {
                "admin": True if adminPerms == 'admin' else False,
                "maintain": False,
                "push": True if adminPerms in ['admin', 'push'] else False,
                "triage": False,
                "pull": True,
            }

        with self._getSession() as s:
            if staffPerms:
                # Grab the 'staff' team id for setting permissions later.
                myURL = f"{self.apiURL}/orgs/{self.org}/teams/staff"
                r = s.get(myURL)
                if r.status_code != 200:
                    self.logger.error("Required 'staff' team was not found in the %s organization. Please create manually.", self.org)
                    return
                staff_team_repos = r.json()['repositories_url']
            if adminPerms:
                # Grab the 'admin' team id for setting permissions later.
                myURL = f"{self.apiURL}/orgs/{self.org}/teams/admin"
                r = s.get(myURL)
                if r.status_code != 200:
                    self.logger.error("Required 'admin' team was not found in the %s organization. Please create manually.", self.org)
                    return
                admin_team_repos = r.json()['repositories_url']

            # Lookup all current repos
            myURL = f"{self.apiURL}/orgs/{self.org}/repos"
            repos = {}
            rCount = 0
            while True:
                r = s.get(myURL)
                if r.status_code == 200:
                    for rCount, item in enumerate(r.json(), rCount+1):
                        if sys.stdout.isatty(): print(f"{rCount:04}", end=' - repo search              \r')
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
            repoCount = len(repos)
            self.logger.info("Found %s matching repositories", repoCount)

            if userPerms:
                # Do all the direct collaborators (students) first, and then the staff team.
                self.logger.info("Inspecting direct collaborator permissions.")
                for rCount, v in enumerate(repos.values(), 1):
                    if sys.stdout.isatty(): print(f"{rCount:04}/{repoCount}", end=' - direct collaborators              \r')
                    owner_name = v['full_name']
                    # Grab the list of direct collaborators
                    # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#list-repository-collaborators
                    u_collab = f"{self.apiURL}/repos/{owner_name}/collaborators"
                    r = s.get(f"{u_collab}?affiliation=direct")
                    if r.status_code == 200:
                        for item in r.json():
                            if item['permissions'] != userPermsD:
                                self.logger.info("Permissions: %s@%s set to %s. Was %s",
                                                item['login'], owner_name, userPerms, item['permissions'])
                                if self.doUpdates:
                                    fix = s.put(f"{u_collab}/{item['login']}", json=userPermsPayload)
                                    if fix.status_code != 204:
                                        self.logger.error("GHE API set user perms status code %s", fix.status_code)
                                        return None
                    else:
                        self.logger.error("%s?affiliation=direct status_code %s", u_collab, r.status_code)
                        return None

                # Go through teams, update all (as user) except staff + admin.
                self.logger.info("Inspecting user team permissions.")
                for rCount, v in enumerate(repos.values(), 1):
                    if sys.stdout.isatty(): print(f"{rCount:04}/{repoCount}", end=' - user teams              \r')
                    owner_name = v['full_name']
                    # Grab the list of direct collaborators
                    # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#list-repository-collaborators
                    t_collab = f"{self.apiURL}/repos/{owner_name}/teams"
                    r = s.get(t_collab)
                    if r.status_code == 200:
                        for item in r.json():
                            if item['name'] in ['staff', 'admin']:
                                continue
                            if item['permission'] != userPerms:
                                self.logger.info("Permissions: (team) %s@%s set to %s. Was %s",
                                                item['name'], owner_name, userPerms, item['permission'])
                                team_repos = item['repositories_url']
                                if self.doUpdates:
                                    fix = s.put(f"{team_repos}/{owner_name}", json=userPermsPayload)
                                    if fix.status_code != 204:
                                        self.logger.error("GHE API set user team perms status code %s", fix.status_code)
                                        return None
                    else:
                        self.logger.error("%s status_code %s", t_collab, r.status_code)
                        return None

            if staffPerms:
                self.logger.info("Inspecting staff team permissions.")
                for rCount, v in enumerate(repos.values(), 1):
                    if sys.stdout.isatty(): print(f"{rCount:04}/{repoCount}", end=' - staff team              \r')
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
                        if self.doUpdates:
                            fix = s.put(u_teams, json=staffPermsPayload)
                            if fix.status_code != 204:
                                self.logger.error("GHE API set staff perms status code %s", fix.status_code)
                                return None

            if adminPerms:
                self.logger.info("Inspecting admin team permissions.")
                for rCount, v in enumerate(repos.values(), 1):
                    if sys.stdout.isatty(): print(f"{rCount:04}/{repoCount}", end=' - admin team              \r')
                    owner_name = v['full_name']
                    # Look up the admin team permissions on the repo.
                    # https://docs.github.com/en/enterprise-server@2.21/rest/reference/teams#check-team-permissions-for-a-repository
                    u_teams = f"{admin_team_repos}/{owner_name}"
                    r = s.get(u_teams, headers={'Accept': 'application/vnd.github.v3.repository+json'})
                    if r.status_code == 200:
                        existingAdminPermsD = r.json()['permissions']
                    elif r.status_code == 404:
                        existingAdminPermsD = None
                    else:
                        self.logger.error(f"%s returned %s", u_teams, r.status_code)
                        return None
                    if existingAdminPermsD != adminPermsD:
                        self.logger.info("Permissions: admin(team)@%s set to %s. Was %s", owner_name, adminPerms, existingAdminPermsD)
                        if self.doUpdates:
                            fix = s.put(u_teams, json=adminPermsPayload)
                            if fix.status_code != 204:
                                self.logger.error("GHE API set admin perms status code %s", fix.status_code)
                                return None

    def deleteAssnRepos(self, assn):
        """ Delete all repos that belong to {assn}.
        This function is really only provided to clean up if a mistake was made on initial repo creation.
        It should never be used as a matter of course...
        REQUIRES personal access token with delete_repo scope."""

        if not self.doUpdates:
            self.logger.warning("DRY RUN - NO CHANGES WILL BE MADE")

        print(f"Are you sure you want to delete all repositories that start with '{assn}_' from org {self.org}?")
        check = input("If you are sure, type 'I am sure.': ")
        if (check != 'I am sure.'):
            self.logger.info("Delete aborted.")
            return

        with self._getSession() as s:
            # Lookup all current repos
            myURL = f"{self.apiURL}/orgs/{self.org}/repos"
            repos = {}
            while True:
                r = s.get(myURL)
                if r.status_code == 200:
                    for item in r.json():
                        if item['name'].startswith(f"{assn}_"):
                            repos[item['name']] = item['url']

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
                    self.logger.error("%s status_code %s", myURL, r.status_code)
                    return None

            for repo,repoURL in repos.items():
                self.logger.info("deleting repo: %s", repo)
                # https://docs.github.com/en/enterprise-server@2.21/rest/reference/repos#delete-a-repository
                if self.doUpdates:
                    r = s.delete(repoURL)
                    if r.status_code == 204:
                        self.logger.debug("deleted repo %s", repoURL)
                    else:
                        self.logger.critical("%s status_code %s", repoURL, r.status_code)
                        return None

    def __repr__(self):
        auth = self.github_headers['Authorization'] if 'Authorization' in self.github_headers else None
        retVal = f"""\
        API URL: {self.apiURL}
  Authorization: {auth}
            Org: {self.org}"""
        if not self.doUpdates:
            retVal += "\n *** DRY RUN - NO CHANGES WILL BE MADE ***"
        return retVal

if __name__ == "__main__":
    #os.environ['GHE_ORG']='CPSCNNN-YYYYS-TN'
    m = manageGHE()
    print(">>> m = manageGHE()")
    print(m)
