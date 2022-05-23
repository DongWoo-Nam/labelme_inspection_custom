# 사용법
## origin_master_backup_220523 브랜치는 22년 5월 23일 기준으로 기존의 master브랜치를 복제 한 것이며 KIST_검수와 다른 점은 이 브랜치의 labelme툴은 검수 시 어노테이션 수정이 불가능하도록 만들어짐 즉 수정없이 승인 및 반려만 가능함
 - 기존 labelme툴에서 클라우드에 있는 이미지를 다운받아 어노테이션 작업을 완료한 것을 검수하기 위해 수정한 툴
    - 툴을 실행했을 때 "검수 대상 목록"탭의 아래쪽에 접속 정보를 입력하고 "접속"버튼을 누르면 config파일 설정에 맞는 버킷에서 파일 다운로드
       - config파일 내부 설명
         - save_driver : 로컬에 이미지와 json파일들이 다운될 때의 driver지정 기본값은 "C드라이버"
         - img_bucket_name : 기본값으로 "process02"이며 이미지가 저장되어있는 버킷이다.
         - down1_bucket_name : 작업자들이 작업한 이미지들의 json파일이 저장되어있는 버킷 "process03"
         - down2_bucket_name : 검수를 하여 nok버킷으로 이동한 파일을 작업자들이 재작업한 json파일이 있는 버킷 "process03-rework"
         - up_bucket_name : 검수를 한뒤 승인을 눌렀을때 json이 이동 될 버킷 "process04"
         - upnok_bucket_name : 검수를 한 뒤 반려를 눌렀을때 json이 이동 될 버킷 "process03-nok"

    - "초기 검수 데이터", "재검수 데이터" 각 탭에 맞는 파일들이 이미지와 json쌍을 이뤄 로컬에 다운로드 됨
       - 이때 파일이 다운로드 될 때에는 각 버킷에 목록을 최신화한 json파일과 로컬에 다운로드 된 파일을 확인하여 해당되지 않는 파일만 다운로드 되도록 되어있음
       - 버킷에 목록을 생성하는 것은 버킷 별 시간이 다르지만 15분 간격으로 최신화가 됨
    - 검수할 파일을 확인 후 "승인"을 누르면 다음 버킷으로 json파일이 업로드 됨
       - 예) process03 -> process04 / process04 -> process05
       - 예) process03-rework -> process04 / process04-rework -> process05
    - 검수할 파일을 확인 후 "반려"를 누르면 해당 버킷의 nok버킷으로 json파일이 업로드 됨 
       - 예) process03 -> process03-nok / process04 -> process04-nok
       - 예) process03-rework -> process03-nok / process04-rework -> process04-nok
    - 업로드가 정상적으로 완료 되면 로컬에서는 이미지 파일과 json파일이 삭제
