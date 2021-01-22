# manageOrg - Python

This provides a simple python object for managing a course Github org.
Say we are teaching CPSCNNN in the TN term of the YYYYS session and have been allocated the org: CPSCNNNN-YYYYS-TN

The manageOrg object in manageOrg.py will allow us to create assignment-specific repositories per user, and will allow us to control permissions to those repos.

Concepts:
* Assignmment repos are of the form `<assignmentName>_<userID>` (one repo per user).
* The tool expects to find a 'staff' team in the org and will assign this team permissions to each repo as directed.
* You can create repos empty, or you can use a 'template' repo.
