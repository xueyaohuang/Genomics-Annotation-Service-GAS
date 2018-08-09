import os
import subprocess
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import errno
from gas import app, db

# post new id onto annotations and save them onto gloabal dictionary
def submit_annotation():
    # Connect to SQS and get the message queue
    try:
        sqs_resource = boto3.resource('sqs', region_name=app.config['AWS_REGION_NAME'])
        huangxy_queue = sqs_resource.get_queue_by_name(QueueName='huangxy_job_requests')
    except Exception as e:
        print(e)
        return
    # Poll the message queue in a loop
    while True:
        # Attempt to read a message from the queue
        response = huangxy_queue.receive_messages(WaitTimeSeconds=20)
        # If message read, extract job parameters from the message body as before
        if response:
            print('Get response successfully.')
            try:
                msg = eval(eval(response[0].body)['Message'])
                user = msg['user_id']
                job_id = msg['job_id']                
                file_name = msg['input_file_name']
                bucket = msg['s3_inputs_bucket']
                key = msg['s3_key_input_file']
                if not job_id or not user or not file_name or not bucket or not key:
                    return jsonify({'code': 500, 'error': 'Cannot get valid parameters.'})
            except Exception as e:
                print(e)
                return
            directory = './data/' + user + '/' + job_id
            # try create new directory
            try:
                os.makedirs(directory)
            except Exception as e:
                print(e)
                return 
            # download file from s3
            try:
                s3 = boto3.resource('s3')
                s3.Bucket(bucket).download_file(key, directory + '/' + file_name)
            except Exception as e:
                print(e)
                return
            # run the annotation
            try:
                subprocess.Popen(['python', 'run.py', directory + '/' + file_name, key, job_id])
            except Exception as e:
                print(e)
                return
            # updata the database
            try:
                dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
                annotation_table = dynamodb.Table('huangxy_annotations')
                annotation_table.update_item(Key={'job_id': job_id},
                                      AttributeUpdates={'job_status': {'Value': 'RUNNING', 'Action': 'PUT'}},
                                      Expected={'job_status': {'Value': 'PENDING', 'ComparisonOperator': 'EQ'}})
                print('Database updated.')
            except Exception as e:
                print(e)
                return
            # delete the SQS message
            try:
                response[0].delete()
                print('Message deleted.')
            except Exception as e:
                print(e)
                return
        else:
            print('There is no response.')
if __name__ == '__main__':
    submit_annotation()   






