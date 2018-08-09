import os
import boto3
import simplejson as json
import time
import uuid

# send requests every 5 seconds to trigger the alarm.
# only test the dynamodb.
while True:
    job_id = str(uuid.uuid4())
    time_now = int(time.time())
    # put new job to dynamodb.
    try:
        dynamodb = boto3.resource('dynamodb', region_name="us-east-1")
        annotation_table = dynamodb.Table("huangxy_annotations")
        annotation_table.put_item(Item={'user_id': 'huangxy', 'job_id': job_id, 'input_file_name': 'test.vcf', 'submit_time': time_now,
                                        's3_inputs_bucket': 'mpcs-students', 's3_key_input_file': 'huangxy/test.vcf', 'job_status': 'PENDING'})
        print('Database updated.')
    except Exception as e:
        print(e)
    # send notification to request queue.
    try:
        client_sns = boto3.client('sns', region_name="us-east-1")
        response = client_sns.publish(TopicArn="arn:aws:sns:us-east-1:127134666975:huangxy_job_requests", 
                                      Message=json.dumps({'user_id': 'huangxy', 'job_id': job_id, 'input_file_name': 'test.vcf', 'submit_time': time_now,
                                                          's3_inputs_bucket': 'mpcs-students', 's3_key_input_file': 'huangxy/test.vcf', 'job_status': 'PENDING'}))
        print('Notification published.')
    except Exception as e:
        print(e)
    # wait for another 5 seconds to send requests.
    time.sleep(5)









