<<<<<<< HEAD
### Run Just Once Please: runjop

RunJOP (Run Just Once Please) is a distributed execution framework to run a command (i.e. a job) only once in a group of servers.

* This can be used together with UNIX/Linux [cron](http://en.wikipedia.org/wiki/Cron) to put a crontab schedule in High Availability (HA).
* The idea is to use [Amazon DynamoDB](http://aws.amazon.com/dynamodb/) to make sure only one server "reserves" the right to execute the command for a certain range of time.
* [Amazon S3](http://aws.amazon.com/s3/) can optionally be used to consolidate the logs of the jobs in a single repository.
* AWS credentials can be passed using AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environmental variables.
* In an EC2 instance a IAM role can be used to give access to DynamoDB/S3 resources.

**This is a personal project. No relation whatsoever exists between this project and my employer.**

### License

Copyright (c) 2013 Danilo Poccia, http://blog.danilopoccia.net

This code is licensed under the The MIT License (MIT). Please see the LICENSE file that accompanies this project for the terms of use.

### Introduction

Running this two commands concurrently on two host (directly or through cron) one of the node will execute the command, the other will not. In this example the command is executed on the "second" node. Debugging info is added to give more information on the execution.

On the "first" node:

    runjop.py --region=eu-west-1 --table myschedule --id my-job --range=10 --node first --s3=s3://BUCKET/mylogs "echo Hello World" --log /tmp/runjop.log -d
    DEBUG:runjop:__init__ '{'node': 'first', 's3log': 's3://BUCKET/mylogs', 'region': 'eu-west-1', 'range': '10', 'debug': True, 'table': 'runjop', 'logfile': '/tmp/runjop.log', 'id': 'my-job'}'
    INFO:runjop:S3 bucket: 'BUCKET'
    INFO:runjop:S3 prefix: 'mylogs/'
    DEBUG:runjop:table 'runjop' not found
    INFO:runjop:table 'runjop' created
    DEBUG:runjop:waiting for table 'runjop' to be active
    DEBUG:runjop:table 'runjop' is active
    DEBUG:runjop:run '['echo Hello World']'
    DEBUG:runjop:now = '2013-02-11 16:03:46'
    DEBUG:runjop:last_item = '{u'node': u'second', u'counter': 1, u'job_id': u'my-ls', u'time': u'2013-02-11 16:03:46'}'
    DEBUG:runjop:last_time_str = '2013-02-11 16:03:46'
    DEBUG:runjop:counter = '1'
    DEBUG:runjop:outside of range of 10 seconds: False
    INFO:runjop:not outside of range of execution
    INFO:runjop:command not executed

On the "second" node:

    runjop.py --region=eu-west-1 --table myschedule --id my-job --range=10 --node second --s3=s3://BUCKET/mylogs "echo Hello World" --log /tmp/runjop.log -d
    DEBUG:runjop:__init__ '{'node': 'second', 's3log': 's3://BUCKET/mylogs', 'region': 'eu-west-1', 'range': '10', 'debug': True, 'table': 'runjop', 'logfile': '/tmp/runjop.log', 'id': 'my-job'}'
    INFO:runjop:S3 bucket: 'BUCKET'
    INFO:runjop:S3 prefix: 'mylogs/'
    DEBUG:runjop:table 'runjop' found
    DEBUG:runjop:waiting for table 'runjop' to be active
    DEBUG:runjop:table 'runjop' is active
    DEBUG:runjop:run '['echo Hello World']'
    DEBUG:runjop:now = '2013-02-11 16:03:46'
    DEBUG:runjop:outside of range of 10 seconds: True
    DEBUG:runjop:put result '{u'ConsumedCapacityUnits': 1.0}'
    DEBUG:runjop:execute_job 'True'
    INFO:runjop:executing command 'echo Hello World'
    INFO:runjop:returncode = 0
    INFO:runjop:output:
    Hello World

    INFO:runjop:output written on s3://danilop-fs/logs/runjop-my-ls-20130211-160346-second-0.log

On DynamoDB the "myschedule" table can be used as an activity log:

    job_id    counter  node      time 
    "my-job"  1        "second"  "2013-02-11 16:03:46"
    "my-job"  2        "first"   "2013-02-11 16:08:52"

The optional S3 log has the following naming convention:

    {table}-{id}-{YYYYMMDD}-{hhmmss}-{node}.log

### Using with cron

The previous example can be scheduled using [cron](http://en.wikipedia.org/wiki/Cron) on more than one hosts, but only one will actually run it. Without the "--node" option the hostname of each node is used. Without the "--range" option the default 300 seconds (5 minutes) range is used.

E.g. to execute the job one minute past midnight (00:01) of every day of the month, of every day of the week:

    1 0 * * *  /somepath/runjop.py --region=eu-west-1 --table myschedule --id my-job --range=10 --s3=s3://BUCKET/mylogs "echo Hello World" --log /var/log/runjop.log

E.g. to	execute	the job to be run every two hours, namely at midnight, 2am, 4am, 6am, 8am, and so on:

    0 */2 * * *  /home/username/runjop.py --region=eu-west-1 --table myschedule --id my-job --range=10 --s3=s3://BUCKET/mylogs "echo Hello World" --log /var/log/runjop.log

### Full Usage

    Usage: runjop.py [options] "<command(s)>"

    RunJOP (Run Just Once Please)

    A distributed execution framework to run a command (i.e. a job) only once in a group of servers.
    This can be used together with UNIX/Linux cron to put a crontab schedule in High Availability (HA).
    The idea is to use Amazon DynamoDB to make sure only one server "reserves" the right
    to execute the command for a certain range of time.
    Amazon S3 can optionally be used to consolidate the logs of the jobs in a single repository.

    Options:
      -h, --help       show this help message and exit
      --region=REGION  AWS region to use for DynamoDB (default is us-east-1)
      --table=TABLE    the DynamoDB table use to check concurrency and log job
		       executions (a new table is created if not found)
      --id=ID          the unique ID identifying this job across multiple servers
      --node=NODE      an identifier for the node (default on this node is
		       current 'hostname')
      --range=S        the range of time (in seconds) in which the execution of
		       the job must be unique (default is 300 seconds)
      --s3=URL         the optional S3 path to put the output of the job in
		       s3://BUCKET[/PATH] format
      --log=FILE       the local filename to use for logs
      -d, --debug      print debug information

=======
runjop
======

RunJOP (Run Just Once Please) is a distributed execution framework to run a command (i.e. a job) only once in a group of servers.
>>>>>>> b135f86829e0ccaf9ec5fb2ccdd3af1ecee02ecb
