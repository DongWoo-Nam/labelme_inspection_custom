import os
from typing import List, Any

import boto3
from IPython.external.qt_for_kernel import QtCore
from qtpy import QtWidgets
from qtpy.QtCore import Qt

import app

# from app import down_access_key, down_access_token
# from app import up_access_key, up_access_token

service_name = 's3'
endpoint_url = 'https://kr.object.ncloudstorage.com'
region_name = 'kr-standard'
# access_key = 'DgEJlJmCpUpELcRyAj9F'
# access_token = 'axcixs48W3YsXxCNmCaYSspUEOHzkXJW0u0b7gmi'

aws_session = boto3.Session(
    aws_access_key_id=app.down_access_key, aws_secret_access_key=app.down_access_token
)

s3_resource = aws_session.resource('s3', endpoint_url=endpoint_url)

s3_down = boto3.client(service_name, aws_access_key_id=app.down_access_key, aws_secret_access_key=app.down_access_token,
                       endpoint_url=endpoint_url)
s3_up = boto3.client(service_name, aws_access_key_id=app.up_access_key, aws_secret_access_key=app.up_access_token,
                     endpoint_url=endpoint_url)


# 버킷 목록 가져오기
def get_bucket_list():
    return s3_down.list_buckets()


s3 = boto3.Session(region_name='kr-standard',
                                     aws_access_key_id = access_key,
                                     aws_secret_access_key = access_token).resource('s3',endpoint_url = 'https://kr.object.ncloudstorage.com') #
def get_object_list_directory_all(bucket_name, prefix='/', extension: object = None):
    bucket = s3_resource.Bucket(bucket_name)

    # 확장자가 지정이 안되었을 경우 기본 확장자 설정
    if extension is None:
        extension = []

    items = []
    for directory in app.down_directory:
        dir = directory + prefix + '/'
        for obj in bucket.objects.filter(Prefix=dir):
            try:
                if len(extension) != 0 and (obj.key.rsplit('.')[1] not in extension):
                    continue
                items.append(obj.key)
            except Exception:
                continue
    return items


# 버킷 내에 오브젝트 목록 가져오기 limit 300
def get_object_list(bucket_name, max_key=300):
    object_response = s3_down.list_objects(Bucket=bucket_name, MaxKeys=max_key)
    return object_response.get('Contents')

# s3_down = s3.resource('s3',endpoint_url = 'https://kr.object.ncloudstorage.com') #
# s3_up = s3.resource('s3',endpoint_url = 'https://kr.object.ncloudstorage.com') #
# s3 path split
def split_s3_key(s3_key):
    key = str(s3_key)
    last_name = key.split('/')[-1]
    return key.replace(last_name, ""), last_name

def isBlank(str):
    if str and str.strip():
        return False
    return True
# 디렉토리 내에 오브젝트 목록 가져오기 (확장자 지정)
def get_object_list_directory(bucket,s3_prefix, pattern=None, after_ts=0):
    global s3
    s3bucket = s3.Bucket(bucket)
    objects = s3bucket.objects.filter(Prefix=s3_prefix)
    filenames = []
    count = 0
    for obj in objects:
        count += 1
        if pattern != None and not pattern in obj.key:
            continue

        last_modified_dt = obj.last_modified
        s3_ts = last_modified_dt.timestamp() * 1000
        if s3_ts > after_ts:
            s3_path, s3_filename = split_s3_key(obj.key)
            # directory check
            if isBlank(s3_filename) or s3_filename.endswith("/"):
                pass
            else:
                filenames.append(s3_path+s3_filename)
    return {
        'directory': s3_prefix,
        'items' : filenames,
        'login_id':pattern
    }


def get_all_keys(**args):
    # 전체 파일목록(key) 반환용 array
    keys = []

    # 1000 개씩 반환되는 list_objects_v2의 결과 paging 처리를 위한 paginator 선언
    # page_iterator = s3_down.get_paginator("list_objects_v2")
    page_iterator = s3_down.list_objects_v2()


    for page in page_iterator.paginate(**args):
        try:
            contents = page["Contents"]
            print(contents)
        except KeyError:
            break

        for item in contents:
            keys.append(item["Key"])

    return keys


# 오브젝트 다운로드
def download_object(bucket_name, object_name, save_path):
    s3_down.download_file(bucket_name, object_name, save_path)


# 오브젝트 다운로드
def download_object(object_name, save_path,s3bucket):
    file_path = os.path.dirname(object_name)
    if os.path.isfile(save_path+object_name):
        return
    if not os.path.exists(save_path+file_path):
        os.makedirs(save_path+file_path)
    s3bucket.download_file(object_name,save_path+object_name)

# 디렉토리 다운로드
def download_directory(bucket_name, directory_name, save_path, login_id):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    s3bucket = s3.Bucket(bucket_name)
    print('directory: %s' % directory_name)

    items = get_object_list_directory_all(bucket_name=bucket_name, prefix=login_id, extension=['png', 'jpeg', 'jpg'])

    total_items = len(items)
    progress = QtWidgets.QProgressDialog("Download files...", QtCore.QString(), 0, total_items)
    progress.setWindowTitle("Downloading files...")
    progress.setCancelButton(None)
    progress.setAutoClose(True)
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)

    i = 0
    for item in items:

        print('item: %d key: %s' % (i, item))
        item_save_path = save_path + '/' + str(item.rsplit('/')[-1])
        download_object(bucket_name=bucket_name, object_name=item, save_path=item_save_path)

        i = i + 1
        print('Downloading files...  %s/%s' % (str(progress.value()), str(total_items)))
        progress.setLabelText = 'Downloading files... ' + str(progress.value()) + '/' + str(total_items)
        progress.setValue(progress.value() + 1)




# 디렉토리 다운로드
def download_directory(bucket_name, directory_name, save_path, login_id):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    s3bucket = s3.Bucket(bucket_name)
    print('directory: %s' % directory_name)

    items = get_object_list_directory(bucket_name, directory_name,login_id)['items']


    progress = QtWidgets.QProgressDialog("Download files...", '', 0, len(items))
    progress.setCancelButton(None)
    progress.setAutoClose(True)
    progress.setWindowModality(Qt.WindowModal)

    for i,file in enumerate(items):
        download_object(file, save_path, s3bucket)
        progress.setValue(i)

# 오브젝트 업로드
def upload_object(bucket_name, local_file_path, directory):
    # 디렉토리 생성(디렉토리가 존재하지 않으면 생성)
    s3bucket = s3.Bucket(bucket_name)
    # s3_up.put_object(Bucket=bucket_name, Key=directory)
    # 업로드할 오브젝트명 설정
    object_name = local_file_path.split("labelme\\")[1].replace(os.path.sep, "/")  # 흰다리 새우에서만 사용 가능
    # 파일 업로드
    print("local_file_path={}".format(local_file_path))
    print("bucket_name={}".format(bucket_name))
    print("object_name={}".format(object_name))
    # s3_up.upload_file(local_file_path, bucket_name, object_name)
    s3bucket.upload_file(local_file_path,object_name)



# 오브젝트 업로드
def upload_object(bucket_name, local_file_path, directory):
    # 디렉토리 생성(디렉토리가 존재하지 않으면 생성)
    s3_up.put_object(Bucket=bucket_name, Key=directory)
    # 업로드할 오브젝트명 설정
    object_name = directory + "/" + local_file_path.rsplit(os.path.sep)[-1]
    # 파일 업로드
    print("local_file_path={}".format(local_file_path))
    print("bucket_name={}".format(bucket_name))
    print("object_name={}".format(object_name))
    s3_up.upload_file(local_file_path, bucket_name, object_name)


# 디렉토리 업로드
def upload_directory(bucket_name, local_folder_path, directory):
    try:
        # 업로드할 디렉토리 설정
        upload_directory = directory + '/' + local_folder_path.rsplit('/')[-1]
        # 업로드할 파일목록
        filenames = os.listdir(local_folder_path)

        for filename in filenames:
            # 업도르할 파일의 경로 설정
            full_filename = os.path.join(local_folder_path, filename)
            # 파일 업로드
            upload_object(bucket_name, full_filename, upload_directory)
    except FileNotFoundError as NFE:
        print(NFE)
    except Exception as E:
        print(E)


if __name__ == '__main__':
    download_directory('ai-object-storage', 'labelme/download/01062537326', "C:/Users/admin/Documents/labelme")

    # 버킷 목록 가져오기
#    response = get_bucket_list()
#    print(response)

#    upload_directory(bucket_name='ai-object-storage',
#                     local_folder_path='/Users/hoseobkim/Documents/work/EchossTech/test', directory='upload_test')

# downloadDirectory(bucket_name='ai-object-storage', directory_name=directory, save_path='/Users/hoseobkim/Documents/work/EchossTech/test')


# objectResponse = get_object_list_directory(bucket_name='ai-object-storage', max_key=max_key,
#                                            directory_path=directory, extension=exts)
#
# print(objectResponse)
#
# downloadObject('ai-object-storage', 'shrimp/2021-07-28/tomato_g_test2.jpg', '/Users/hoseobkim/Documents/work/EchossTech/tomato_g_test2.jpg')
