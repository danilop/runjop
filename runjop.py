#!/usr/bin/env python

import subprocess
import logging
import datetime
import urlparse
import socket

import boto
import boto.dynamodb
import boto.dynamodb.layer2

from boto.s3.key import Key

from optparse import OptionParser

class RunJOP():

    def __init__(self, options):
        logger.debug("__init__ '%s'" % options)

        # Options Parsing

        global debug
        debug = options.debug

        self.date_format_db = '%Y-%m-%d %H:%M:%S'
        self.date_format_s3 = '%Y%m%d-%H%M%S'

        if options.table:
            self.table_name = options.table
        else:
            errorAndExit("a DynamoDB table to check concurrency and log job executions must be provided")

        if options.id:
            self.id = options.id
        else:
            errorAndExit("a unique ID identifying this job across multiple servers must be provided")

        if options.node:
            self.node = options.node
        else:
            errorAndExit("a unique identifier for the node must be provided")

        if options.range > 0:
            self.range = int(options.range)
        else:
            errorAndExit("the range (in seconds) must be greater than 0")

        if options.s3log:
            s3url = urlparse.urlparse(options.s3log.lower())
            if s3url.scheme != 's3':
                errorAndExit("The S3 path to mount must be in URL format: s3://BUCKET/PATH")
            self.s3_bucket_name = s3url.netloc
            if self.s3_bucket_name == '':
                errorAndExit("The S3 bucket cannot be empty")
            logger.info("S3 bucket: '%s'" % self.s3_bucket_name)
            self.s3_prefix = s3url.path.strip('/')
            if self.s3_prefix:
                self.s3_prefix += '/'
            logger.info("S3 prefix: '%s'" % self.s3_prefix)
        else:
            self.s3_bucket_name = None

        # AWS Initialization

        self.aws_region = options.region # Not used by S3

        if self.s3_bucket_name:
            try:
                s3 = boto.connect_s3() # Not using AWS region for S3, got an error otherwise, depending on the bucket             
            except boto.exception.NoAuthHandlerFound:
                errorAndExit("no AWS credentials found")
            if not s3:
                errorAndExit("no S3 connection")
            try:
                self.s3_bucket = s3.get_bucket(self.s3_bucket_name)
            except boto.exception.S3ResponseError, e:
                errorAndExit(e.body['message'])

        dynamodb = boto.dynamodb.connect_to_region(self.aws_region)

        self.table = None

        while self.table == None:
            try:
                self.table = dynamodb.get_table(self.table_name)
                logger.debug("table '%s' found" % self.table_name)
            except boto.exception.DynamoDBResponseError:
                logger.debug("table '%s' not found" % self.table_name)
                schema = boto.dynamodb.schema.Schema.create(hash_key=('job_id', 'S'), range_key=('counter', 'N'))
                try:
                    # 1 read/sec + 1 write/sec should be enough
                    self.table = dynamodb.create_table(self.table_name, schema, read_units=1, write_units=1)
                    logger.info("table '%s' created" % self.table_name)
                except boto.exception.DynamoDBResponseError, e:
                    logger.debug("boto.exception.DynamoDBResponseError: %s" % e.body['message'])
                    if u'The rate of control plane requests made by this account is too high' in e.body['message']:
                        pass
                    elif u'Table is being created' in e.body['message']:
                        pass
                    else:
                        raise

        logger.debug("waiting for table '%s' to be active" % self.table_name)
        self.table.refresh(wait_for_active=True, retry_seconds=5)
        logger.debug("table '%s' is active" % self.table_name)

    def run(self, args):
        logger.debug("run '%s'" % args)

        now = datetime.datetime.utcnow()
        logger.debug("now = '%s'" % now.strftime(self.date_format_db))

        result = self.table.query(hash_key=self.id, max_results=1,
                                  consistent_read=True, scan_index_forward=False)

        outside_of_range = False
        counter = 0

        try:
            if result.count > 0:
                last_item = result.response['Items'][0]
                logger.debug("last_item = '%s'" % last_item)
                last_time_str = last_item['time']
                counter = last_item['counter']
                logger.debug("last_time_str = '%s'" % last_time_str)
                logger.debug("counter = '%s'" % counter)
                last_time = datetime.datetime.strptime(last_time_str, self.date_format_db)
                delta = datetime.timedelta(seconds=self.range)
                if abs(now - last_time) > delta:
                    outside_of_range = True
            else:
                outside_of_range = True
        except boto.exception.DynamoDBResponseError:
            logger.debug("DynamoDBResponseError: %s" % e.body['message'])
            outside_of_range = True

        logger.debug("outside of range of %i seconds: %s" % (self.range, outside_of_range))

        if not outside_of_range:

            logger.info("not outside of range of execution")
            logger.info("command not executed")
            return

        counter += 1
        execute_job = False

        new_item = self.table.new_item(hash_key=self.id, range_key=counter,
                                       attrs={'time':now.strftime(self.date_format_db),'node':self.node})
        try:
            result = new_item.put(expected_value={'job_id':False})
            execute_job = True
        except boto.dynamodb.exceptions.DynamoDBConditionalCheckFailedError:
            logger.debug("DynamoDBConditionalCheckFailedError: %s" % e.body['message'])
            pass
        except boto.exception.DynamoDBResponseError:
            logger.debug("DynamoDBResponseError: %s" % e.body['message'])
            pass

        logger.debug("put result '%s'" % result)
        logger.debug("execute_job '%s'" % execute_job)

        if not execute_job:

            logger.info("taken by another node before update")
            logger.info("command not executed")
            return

        command = ' '.join(args)

        logger.info("executing command '%s'" % command)
            
        try:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
            returncode = 0
        except subprocess.CalledProcessError, e:
            output = e.output
            returncode = e.returncode
            
        logger.info("returncode = %i" % returncode)
        logger.info("output:\n%s" % output)

        key_name = self.s3_prefix + '-'.join([self.table_name, self.id,
                                              now.strftime(self.date_format_s3),
                                              self.node, str(returncode)]) + '.log'
                
        k = Key(self.s3_bucket)
        k.key = key_name
        content = '\n'.join(["command:", command, "output:", output])
        k.set_contents_from_string(content, headers={'Content-Type': 'text/plain'})
        logger.info("output written on s3://%s/%s" % (self.s3_bucket_name, key_name))

def errorAndExit(error, exitCode=1):
    logger.error(error + ", use -h for help.")
    exit(exitCode)

if __name__ == '__main__':

    usage = """%prog [options] "<command(s)>"

RunJOP (Run Just Once Please) is a distributed execution framework
to run a command (i.e. a job) only once in a group of servers
and can be used together with UNIX/Linux cron to put a crontab schedule in High Availability (HA).

The idea is to use Amazon DynamoDB to make sure only one server "reserves" the right
to execute the command for a certain range of time.
Amazon S3 can optionally be used to consolidate the logs of the jobs in a single repository.
AWS credentials can be passed using AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environmental variables.
In an EC2 instance a IAM role can be used to give access to DynamoDB/S3 resources."""

    parser = OptionParser(usage=usage)

    parser.add_option("--region", dest="region",
                      help="AWS region to use for DynamoDB (default is %default)",
                      metavar="REGION", default="us-east-1")

    parser.add_option("--table", dest="table",
                      help="the DynamoDB table use to check concurrency and log job executions (a new table is created if not found)",
                      metavar="TABLE")

    parser.add_option("--id", dest="id",
                      help="the unique ID identifying this job across multiple servers",
                      metavar="ID")

    parser.add_option("--node", dest="node",
                      help="an identifier for the node (default on this node is '%default')",
                      metavar="NODE", default=socket.gethostname())

    parser.add_option("--range", dest="range",
                      help="the range of time (in seconds) in which the execution of the job must be unique (default is %default seconds)",
                      metavar="S", default="300")

    parser.add_option("--s3", dest="s3log",
                      help="the optional S3 path to put the output of the job in s3://BUCKET[/PATH] format",
                      metavar="URL", default="")

    parser.add_option("--log", dest="logfile",
                      help="the local filename to use for logs", metavar="FILE", default="")

    parser.add_option("-d", "--debug", action="store_true", dest="debug", default=False,
                      help="print debug information")

    (options, args) = parser.parse_args()

    logging.basicConfig()
    logger = logging.getLogger('runjop')

    if options.logfile != '':
        logHandler = logging.handlers.RotatingFileHandler(options.logfile, maxBytes=1024*1024, backupCount=10)
        logger.addHandler(logHandler)

    if options.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if len(args) < 1:
        errorAndExit("at least a command must be provided")

    runjop = RunJOP(options)

    runjop.run(args)
