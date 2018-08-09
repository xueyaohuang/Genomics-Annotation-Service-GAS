# Capstone

### Name: Xueyao Huang             
### CNetID: huangxy

## Overview

In this project, the front end gas web and back end annotators use out scaling group, while the utils uses normal instances.

The out scaling group can scale out or scale in depends on the usage, ranging from 2 to 10 instances. The utils instance has three python files running, i.e. archive_restore for retrieving premium users' results back, results_notify for sending emails to users, and results_archive for archive free users' results. 


## Answer to questions:

#### Exercise 2:
I use Javascript in the upload form to check the file size when a free user is requesting an annotation. In the views.py, I set the size for free users and premium users. In the annotate.html check_size function, if the size corresponds to free user, the page will redirect to subscribe page and onSubmit attribute will be set to false, so it will not jump to annotation page. go_to_subscribe function will redirect to subscribe page. onclick="showFileSize()" will show the input file size.

#### Exercise 7:
I use message queues to do the periodic background task. In the archive_to_glacier function, I keep receiving messages from sqs. If the job should NOT be archived to glacier, I will create a list to store its job ID and prevent to archive it. If it should be archived to glacier, I will check the time elapsed from the job being completed.  Only when the complete time is greater than 30 minutes, I will move the job to glacier and delete the response. <br>
The reason I use message queue is that it is more scalable than polling the database. If I use polling the database, I have to scan all the jobs. If there are lots of job records in the database, it consumes lots of time. Moreover, it is simpler than workflow service like Amazon SWF. I tried to utilize SWF, but with very few examples, I cannot make it work properly.

#### Exercise 9:
I use message queues to do the archive retrieval, i.e. AWS_SNS_ARCHIVE_RETRIEVE_TOPIC sns and AWS_SQS_ARCHIVE_RETRIEVE sqs. In views.py subscribe function, I will check if a job has archive_id attribute. I use a while loop to guarantee that glacier initiate job successfully, since there maybe capacity insufficient problem. It should be noticed that SNSTopic is a must since it is used to check if the job is complete or not. In archive_restore.py, I use glacier.get_job_output to get the job back and do the table scan to get the s3_result_key and job_id. And then put results back to s3.<br>
The reason I use message queue is that it is scalable and it can decouple different farm.
#### Exercise 13:
I set a larger test load (300 users, at 30/sec.) on the web console. The locust test is shown below.<br>
<br>
<img src="https://github.com/mpcs-cc/cp-xueyaohuang/blob/master/screen_shot/locust_web" width="600">
<br>
<br>
Before the locust test runs, I have 2 web instances. After the locust test runs for a while, the instances will increase according to the auto scaling policy. As shown in the figure, it increased to 7 instances after the tests runs for about 20 minutes. More instances launch because the requests exceed the scale out policy and triggered the alarm.<br>
<br>
<img src="https://github.com/mpcs-cc/cp-xueyaohuang/blob/master/screen_shot/web_scale_out" width="600">
<br>
<br>
Then I stopped the locust test the scale in alarm was not triggered since the response time was still above 10 ms. I waited for a very long time, after about 2 hours the response time began to decrease below 10ms. So the number of instances began to decrease. At last the web instance decrease from 7 to 2 again as shown below.<br>
<br>
<img src="https://github.com/mpcs-cc/cp-xueyaohuang/blob/master/screen_shot/web_scale_in" width="600">
<br>
<br>
#### Exercise 14:
Please see the test_ann_auto_scaling.py for simulating the load. I put a new job to dynamodb and send notification to request queue every 5 seconds to trigger the annotator scale out alarm. After about 3 minutes when I run the script, the annotator instance began to increase as shown below. 
<br>
<br>
<img src="https://github.com/mpcs-cc/cp-xueyaohuang/blob/master/screen_shot/ann_scale_out" width="600">
<br>
<br>
When the number of instances reached 6 I stopped the script since there were too many emails. The annotator scale in alarm was triggered very soon. The number of annotator instances began to decrease. After about 30 minutes, the number of annotator instances decreased back to 2.
<br>
<br>
<img src="https://github.com/mpcs-cc/cp-xueyaohuang/blob/master/screen_shot/ann_sclae_in" width="600">
<br>
<br>




## References:
http://boto3.readthedocs.io/en/latest/ <br>
https://aws.amazon.com/documentation/  <br>
https://stripe.com/docs/api#authentication <br>
http://boto3.readthedocs.io/en/latest/guide/migrations3.html#creating-a-bucket<br>
https://sysadmins.co.za/interfacing-amazon-dynamodb-with-python-using-boto3/<br>
https://docs.aws.amazon.com/autoscaling/ec2/userguide/GettingStartedTutorial.html<br>
https://docs.aws.amazon.com/autoscaling/ec2/userguide/attach-instance-asg.html<br>
https://bradmontgomery.net/blog/sending-sms-messages-amazon-sns-and-python/<br>
https://stackoverflow.com/questions/3717793/javascript-file-upload-size-validation <br>
https://stackoverflow.com/questions/30249069/listing-contents-of-a-bucket-with-boto3 <br>
https://cloudacademy.com/blog/aws-cloudwatch-monitoring/<br>
https://boto3.readthedocs.io/en/latest/reference/services/cloudformation.html<br>
https://stackoverflow.com/questions/32721847/boto3-and-swf-example-needed <br>
https://stackoverflow.com/questions/35758924/how-do-we-query-on-a-secondary-index-of-dynamodb-using-boto3<br>
https://stackoverflow.com/questions/31918960/boto3-to-download-all-files-from-a-s3-bucket?rq=1 <br>



