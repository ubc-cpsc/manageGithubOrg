# manageOrg - Python

This provides a simple method for managing a course Github org.

The manageOrg object in manageOrg.py will allow us to create assignment-specific repositories per user, and will allow us to control permissions to those repos.

## Configuration

Say we are teaching CPSCNNN in term M of session YYYYS and have been allocated the github org:
> __CPSCNNNN-YYYYS-TM__

Changes to github are authorized via a personal access token; to create a token,
visit [github.students.cs.ubc.ca/settings/tokens](https://github.students.cs.ubc.ca/settings/tokens).
Create a token with scope 'repo' (Full control of private repositories).

The tool is configured via environment variables. For example, you could put something like this in your `~/.bash_profile`:

    export GHE_ORG=CPSCNNN-YYYYS-TM
    export GHE_TOKEN=personalaccesstoken

Alternatively, you can set environment variables in a custom python script (don't change manageGHE.py):

    #!/usr/bin/python3
    import os
    os.environ['GHE_ORG']='CPSCNNN-YYYYS-TM'
    os.environ['GHE_TOKEN']='personalaccesstoken'

Manual access to the tool is easy; set the above environment variables and run:

    python3 -i manageGHE.py

This will leave you at the python command prompt as if you had done this instead:

    $ python3
    >>> from manageGHE import manageGHE
    >>> m = manageGHE()

## Student Listing

You may have a 'students' team that contains your automatically-synchronized classlist. (If you do not, ask help@cs.ubc.ca and we'll configure it for you.)
You can query the membership of this team via:

    students = m.getTeamMembership('students')

## Repositories

Concepts:
* Assignmment repos are of the form `<assignmentName>_<userID>` (one repo per user).
* The tool expects to find a 'staff' team in the org and will assign this team permissions to each repo as directed.
* You can create repos empty, or you can use a 'template' repo.
* All changes are logged specifically.

### Repo creation
Subsequent runs of this command simply ignore repos that already exist (by name).

    m.createAssnRepos('assn1', students)
    m.createAssnRepos('assn1', students, template='CPSCNNN-YYYYS-TM/assn1Template')

### Permission setting
Note the default permissions for userPerms/staffPerms/adminPerms is None, which means don't do anything.
Only explicitly specified permissions will be updated.

    m.setAssnPerms('assn1', userPerms='push')

### Repo deletion
A function is provided to delete repos. _Please use with caution._ Your token will need the `delete_repo` scope.
This function should only be used in the course of testing the operation of the tool.
It is recommended to remove the `delete_repo` token scope immediately after successful cleanup.

    m.deleteAssnRepos('assn1')
