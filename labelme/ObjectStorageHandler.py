import io
import os
from typing import List, Any

import boto3
from IPython.external.qt_for_kernel import QtCore
from qtpy import QtWidgets
from qtpy.QtCore import Qt

import json
import datetime

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

s3 = boto3.Session(region_name='kr-standard',
                   aws_access_key_id=app.down_access_key,
                   aws_secret_access_key=app.down_access_token).resource('s3',
                                                                         endpoint_url='https://kr.object.ncloudstorage.com')  #


# 버킷 목록 가져오기
def get_bucket_list():
    return s3_down.list_buckets()


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
# s3 path split: 다운로드 경로 배열변경
def split_s3_key(s3_key):
    key = str(s3_key)
    last_name = key.split('/')[-1]
    return key.replace(last_name, ""), last_name


# 빈문자열 체크
def is_blank(str):
    if str and str.strip():
        return False
    return True


# 디렉토리 내에 오브젝트 목록 가져오기 (확장자 지정)
def get_object_list_directory(bucket, s3_prefix, pattern=None, after_ts=0):
    global s3
    s3bucket = s3.Bucket(bucket)
    objects = s3bucket.objects.filter(Prefix=s3_prefix)
    filenames = []
    count = 0
    for obj in objects:
        count += 1
        if pattern is not None and not pattern in obj.key:
            continue

        last_modified_dt = obj.last_modified
        s3_ts = last_modified_dt.timestamp() * 1000
        if s3_ts > after_ts:
            s3_path, s3_filename = split_s3_key(obj.key)
            # directory check
            if is_blank(s3_filename) or s3_filename.endswith("/"):
                pass
            else:
                filenames.append(s3_path + s3_filename)
    return {
        'directory': s3_prefix,
        'items': filenames,
        'login_id': pattern
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
def download_object_by_client(bucket_name, object_name, save_path):
    file_path, file_name = os.path.split(object_name)
    if not os.path.exists(save_path + file_path):
        os.makedirs(save_path + file_path)
    if (os.path.isfile(save_path + object_name)) | (file_name+".bak" in os.listdir(save_path + file_path)):  # 작업 완료 파일 재 다운로드 방지 by dwnam
        return
    s3_down.download_file(bucket_name, object_name, save_path + object_name)
    print("Downloading object : %s" % object_name)

def get_bak_file_name(file_name):
    file_ext = os.path.splitext(file_name)
    return file_ext[0] + "_" + file_ext[1][1:] + ".bak"

def log_by_bucket_name(log_path, msg, bucket_name):
    s3bucket = s3.Bucket(bucket_name)
    log(log_path, msg, s3bucket)

def log(log_path, msg, s3bucket):
    dt_now = datetime.datetime.now()
    szDate = dt_now.strftime('%Y%m%d')
    szTime = dt_now.strftime('%H:%M:%S') + " "
    log_file_name = app.down_access_key + "_" + szDate + ".txt"
    log_full_name = log_path + log_file_name

    with open(log_full_name, "a") as f:
        f.write(szTime + msg + "\n")

    # print("src=" + log_full_name)
    # print("tgt=" + "logs/" + log_file_name)
    s3bucket.upload_file(log_full_name, "logs/" + log_file_name)

# 오브젝트 다운로드
def download_object(object_name, save_path, s3bucket, logging=True):
    file_path, file_name = os.path.split(object_name)

    s3bucket.download_file(object_name, save_path + object_name)
    if logging:
        log(save_path, "download %s" % file_name, s3bucket)
    print("Downloading object : %s" % object_name)


# 디렉토리 다운로드(client 사용)
def download_directory_by_client(bucket_name, directory_name, save_path, login_id):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    s3bucket = s3.Bucket(bucket_name)
    print('bucket: %s' % bucket_name)
    print('directory: %s' % directory_name)

    items = get_object_list_directory_all(bucket_name=bucket_name, prefix=login_id, extension=['png', 'jpeg', 'jpg'])

    total_items = len(items)
    progress = QtWidgets.QProgressDialog("Download files...", "", 0, total_items)
    progress.setWindowTitle("Downloading files...")
    progress.setCancelButton(None)
    progress.setAutoClose(True)
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)

    for item in items:
        print('item: %d key: %s' % (progress.value(), item))
        # item_save_path = save_path + '/' + str(item.rsplit('/')[-1])
        download_object_by_client(bucket_name=bucket_name, object_name=item, save_path=save_path)

        print('Downloading files...  %s/%s' % (str(progress.value()), str(total_items)))
        progress.setLabelText = 'Downloading files... ' + str(progress.value()) + '/' + str(total_items)
        progress.setValue(progress.value() + 1)


# 디렉토리 다운로드
def download_directory(bucket_name, directory_name, save_path, login_id):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    s3bucket = s3.Bucket(bucket_name)
    print('bucket: %s' % bucket_name)
    print('directory: %s' % directory_name)

    items = get_object_list_directory(bucket_name, directory_name, login_id)['items']

    progress = QtWidgets.QProgressDialog("Download files...", '', 0, len(items))
    progress.setCancelButton(None)
    progress.setAutoClose(True)
    progress.setWindowModality(Qt.WindowModal)

    for i, file in enumerate(items):
        download_object(file, save_path, s3bucket)
        progress.setValue(i)

def download_directory_image(bucket_name, img_bucket_name, directory_name, save_path, login_id):
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    s3bucket = s3.Bucket(bucket_name)
    s3bucket2 = s3.Bucket(img_bucket_name)
    # print('bucket: %s' % bucket_name)
    # print('directory: %s' % directory_name)

    # config 상 down1_bucket_name의 데이터
    down_bucket_data = read_file(bucket_name, f"{bucket_name}_object_list.json")  # 배치로 생성된 object list 읽기
    down_bucket_data.seek(0)
    dict_down = down_bucket_data.read().decode()
    data_down = json.loads(dict_down)
    down_bucket_items_origin = [x for x in data_down[directory_name.split("/")[0]] if login_id in x]  # directory_name.split("/")[0]는 'shrimp' or 'tomato' or 'paprika'
    down_bucket_items_origin = [x for x in down_bucket_items_origin if directory_name in x]
    down_bucket_items_origin = [x for x in down_bucket_items_origin if x.endswith(tuple((".json")))]  # proc02이기때문에 이미지의 확장자만 가지고 오기
    down_bucket_items_origin = [x.split(".")[0] for x in down_bucket_items_origin]  # .json과 비교하기 위하여 뒤의 확장자 제외하고 이름 비교

    # config 상 up_bucket_name의 데이터
    up_bucket_data = read_file(app.up_bucket_name, f"{app.up_bucket_name}_object_list.json")  # 배치로 생성된 object list 읽기
    up_bucket_data.seek(0)
    dict_up = up_bucket_data.read().decode()
    data_up = json.loads(dict_up)
    up_bucket_items_origin = [x for x in data_up[directory_name.split("/")[0]] if login_id in x]  # directory_name.split("/")[0]는 'shrimp' or 'tomato' or 'paprika'
    up_bucket_items_origin = [x for x in up_bucket_items_origin if directory_name in x]
    up_bucket_items_origin = [x for x in up_bucket_items_origin if x.endswith(tuple((".json")))]  # proc02이기때문에 이미지의 확장자만 가지고 오기
    up_bucket_items_origin = [x.split(".")[0] for x in up_bucket_items_origin]  # .json과 비교하기 위하여 뒤의 확장자 제외하고 이름 비교

    # config 상 upnok_bucket_name의 데이터
    up_nok_bucket_data = read_file(app.upnok_bucket_name, f"{app.upnok_bucket_name}_object_list.json")  # 배치로 생성된 object list 읽기
    up_nok_bucket_data.seek(0)
    dict_upnok = up_nok_bucket_data.read().decode()
    data_upnok = json.loads(dict_upnok)
    up_nok_bucket_items_origin = [x for x in data_upnok[directory_name.split("/")[0]] if login_id in x]  # directory_name.split("/")[0]는 'shrimp' or 'tomato' or 'paprika'
    up_nok_bucket_items_origin = [x for x in up_nok_bucket_items_origin if directory_name in x]
    up_nok_bucket_items_origin = [x for x in up_nok_bucket_items_origin if x.endswith(tuple((".json")))]  # proc02이기때문에 이미지의 확장자만 가지고 오기
    up_nok_bucket_items_origin = [x.split(".")[0] for x in up_nok_bucket_items_origin]  # .json과 비교하기 위하여 뒤의 확장자 제외하고 이름 비교

    # 조건에 부합하는 이미지만 list에 넣기 위한 작업
    # 예를들어 1차 검수자이면 process03의 작업 완료 목록에서 process04의 1차 검수 완료 목록을 빼고 process03-nok의 목록을 뺀 데이터가 1차 검수를 할 목록이 되는 것임
    not_working = list((set(down_bucket_items_origin) - set(up_bucket_items_origin)) - set(up_nok_bucket_items_origin))
    not_working.sort()
    items = [x + ".json" for x in not_working]
    # items = get_object_list_directory(bucket_name, directory_name, login_id)['items']  # 기존 스크립트 주석처리 211220 by dwnam

    progress = QtWidgets.QProgressDialog("Download files...", '', 0, len(items))
    progress.setCancelButton(None)
    progress.setAutoClose(True)
    progress.setWindowModality(Qt.WindowModal)

    json_num = 0
    img_num = 0

    for i, file in enumerate(items):
        file_path, file_name = os.path.split(file)
        if not os.path.exists(save_path + file_path):
            os.makedirs(save_path + file_path)
        if (os.path.isfile(save_path + file)) | (
                get_bak_file_name(file_name) in os.listdir(save_path + file_path)):  # 작업 완료 파일 재 다운로드 방지 by dwnam
            progress.setValue(i)
            continue

        download_object(file, save_path, s3bucket)
        json_num = json_num + 1

        if file.endswith("json"):
            local_json = os.path.join(save_path[:-2], file)
            # print("bak=" + get_bak_file_name(local_json))
            with open(local_json, 'r') as f:
                json_data = json.load(f)
            img_file = os.path.dirname(file) + "/" + json_data['imagePath']
            if not os.path.isfile(img_file):  # 작업 완료 파일 재 다운로드 방지 by dwnam
                if check(img_bucket_name, img_file):  # json이랑 매칭되는 이미지가 있을 경우 다운로드
                    download_object(img_file, save_path, s3bucket2, False)
                    img_num = img_num + 1
                else:
                    log(save_path, login_id + f'파일 짝이 맞지 않습니다. : {img_file} / {file}',s3bucket)  # 짝이 맞지 않았을때 로그 생성 211222
        progress.setValue(i)

    log(save_path, login_id + " downloaded %d json files, %d image files" % (json_num, img_num), s3bucket)

def upload_object_simply(bucket_name, src_file_path, tgt_file_path):
    print("bucket_name={}".format(bucket_name))
    print("src_file_path={}".format(src_file_path))
    print("tgt_file_path={}".format(tgt_file_path))
    s3bucket = s3.Bucket(bucket_name)
    s3bucket.upload_file(src_file_path, tgt_file_path)

# 오브젝트 업로드
def upload_object(bucket_name, local_file_path, directory):
    # 디렉토리 생성(디렉토리가 존재하지 않으면 생성)
    s3bucket = s3.Bucket(bucket_name)
    # s3_up.put_object(Bucket=bucket_name, Key=directory)
    # 업로드할 오브젝트명 설정
    object_name = local_file_path.split(r'labelme\\')[1].replace(os.path.sep, "/")  # 흰다리 새우 수정 by dwnam 210913
    # 파일 업로드
    print("local_file_path={}".format(local_file_path))
    print("bucket_name={}".format(bucket_name))
    print("object_name={}".format(object_name))
    # s3_up.upload_file(local_file_path, bucket_name, object_name)
    s3bucket.upload_file(local_file_path, object_name)


# 오브젝트 업로드
def upload_object_by_client(bucket_name, local_file_path, directory):
    # 디렉토리 생성(디렉토리가 존재하지 않으면 생성)
    s3_up.put_object(Bucket=bucket_name, Key=directory)
    # 업로드할 오브젝트명 설정
    object_name = local_file_path.split(r'labelme\\')[1].replace(os.path.sep, "/")  # 피노타이핑 수정 by dwnam 210913
    # object_name = directory + "/" + local_file_path.rsplit(os.path.sep)[-1]
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

def delete_object(bucket_name, object_name):
    s3bucket = s3.Bucket(bucket_name)
    s3bucket.delete_objects(Delete={
        'Objects': [
            {
                'Key': object_name
            }
        ]
    })

def read_file(bucket_name, file_name):
    s3bucket = s3.Bucket(bucket_name)
    file = io.BytesIO()
    obj = s3bucket.Object(file_name)
    obj.download_fileobj(file)
    return file

from botocore.exceptions import ClientError
def check(bucket, key):
    global s3
    try:
        s3.Object(bucket, key).load()
    except ClientError as e:
        return int(e.response['Error']['Code']) != 404
    return True


if __name__ == '__main__':
    pass
    # download_directory('ai-object-storage', 'labelme/download/01062537326', "C:/Users/admin/Documents/labelme")

