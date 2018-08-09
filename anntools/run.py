# Copyright (C) 2011-2018 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import sys
import time
import driver
import boto3
import os
import os.path
import configparser
from flask import Flask
import simplejson as json


# app = Flask(__name__)
# app.config.from_object(os.environ['GAS_SETTINGS'])

"""A rudimentary timer for coarse-grained profiling
"""


class Timer(object):
    def __init__(self, verbose=True):
        self.verbose = verbose

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.secs = self.end - self.start
        if self.verbose:
            print("Total runtime: {0:.6f} seconds".format(self.secs))

# copies the annotated results file and the associated log from AnnTools instance to the S3 gas-results bucket.
def upload_file(s3, directory_file, key):
    s3.meta.client.upload_file(directory_file + '.annot.vcf', 'gas-results', key + '.annot.vcf')
    s3.meta.client.upload_file(directory_file + '.vcf.count.log', 'gas-results', key + '.vcf.count.log')
    print("Update results and log files successfully.")

def update_database(annotation_table, key, job_id):
    annotation_table.update_item(Key={'job_id': job_id},
                          AttributeUpdates={'job_status': {'Value': 'COMPLETED', 'Action': 'PUT'},
                                            's3_results_bucket': {'Value': 'gas-results', 'Action': 'PUT'},
                                            's3_key_result_file': {'Value': key + '.annot.vcf', 'Action': 'PUT'},
                                            's3_key_log_file': {'Value': key + '.vcf.count.log', 'Action': 'PUT'},
                                            'complete_time': {'Value': int(time.time()), 'Action': 'PUT'}},
                          Expected={'job_status': {'Value': 'RUNNING', 'ComparisonOperator': 'EQ'}})
    print('Update database successfully.')

# delete files on the AnnTools instance
def remove_file(task_file, directory_file, task_dir):
    os.remove(task_file)
    os.remove(directory_file + '.annot.vcf')
    os.remove(directory_file + '.vcf.count.log')
    os.rmdir(task_dir)
    print('Delete task files successfully.')

if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read(os.path.abspath('./configini.ini'))
    aws_config = config['ann']
    if len(sys.argv) > 3:
        with Timer():
            driver.run(sys.argv[1], 'vcf')
        print('Finish annotation successfully.')
        # upload results and logs
        try:
            s3 = boto3.resource('s3', region_name=aws_config['AWS_REGION_NAME'])
            task_file = sys.argv[1]
            directory_file = task_file.replace('.vcf', '')
            key = sys.argv[2].replace('.vcf', '')
            upload_file(s3, directory_file, key)
        except Exception as e:
            print(e)
            print('Cannot upload files.')
        # remove files on AnnTools instance
        try:
            task_file = sys.argv[1]
            directory_file = task_file.replace('.vcf', '')
            task_dir = os.path.dirname(task_file)
            remove_file(task_file, directory_file, task_dir)
        except Exception as e:
            print(e)
            print('Cannot remove files on AnnTools instance.')
        # update the database
        try:
            job_id = sys.argv[3]
            key = sys.argv[2].replace('.vcf', '')
            dynamodb = boto3.resource('dynamodb', region_name=aws_config['AWS_REGION_NAME'])
            annotation_table = dynamodb.Table(aws_config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
            update_database(annotation_table, key, job_id)
        except Exception as e:
            print(e)
            print('Cannot update the database.')
        # publish a notification to this topic
        try:
            sns = boto3.client('sns', region_name=aws_config['AWS_REGION_NAME']) 
            sns_response = sns.publish(TopicArn=aws_config['AWS_SNS_JOB_COMPLETE_TOPIC'],
                                       Message=json.dumps(annotation_table.get_item(Key={'job_id': job_id})['Item']))
            print('Notification sent successfully.')
        except Exception as e:
            print(e)
    else:
        print("Please provide a valid .vcf file.")
