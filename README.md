# CGMD mailbox

Queue work for the workstation from any session, branch or machine:

    python3 -m core.hub_mailbox run --kind smoke --timeout 1800

* inbox/<id>.json   request  (cgmd.mailbox.request.v1)
* outbox/<id>.json  result   (cgmd.mailbox.result.v1)

The desk claims at most mailbox_jobs_per_poll jobs per cycle (60 s),
answers them here and never touches the caller branch.
