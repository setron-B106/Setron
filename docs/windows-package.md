# SETRON Windows 실행 안내

## 1. 화면 먼저 둘러보기

1. Windows 10 이상 64비트 PC에서 배포 ZIP의 압축을 풉니다.
2. 압축을 푼 `SETRON` 폴더에서 `SETRON.exe`를 실행합니다. 실행 파일과 `_internal` 폴더는 같은 위치에 둡니다.
3. DB 접속 설정이 없으면 예시 설비가 표시됩니다. 대시보드, 히트맵, 버전 리플레이를 바로 살펴볼 수 있습니다.

배포본에는 Python과 실행 라이브러리가 들어 있습니다. 실제 Excel 자료를 가져오려면 Windows용 데스크톱 Excel에서 해당 파일을 먼저 엽니다.

## 2. MySQL에 자료 저장하기

1. 같은 PC에 MySQL 5.6.19를 실행하고 SETRON용 빈 데이터베이스와 계정을 준비합니다. 계정에는 대상 DB의 테이블 생성·참조 권한과 사용할 데이터의 조회·수정 권한이 필요합니다.
2. 실행 파일 옆의 `setron.env.example`을 `setron.env`로 복사합니다. `SETRON_DB_HOST`에는 로컬 주소를 쓰고 포트, DB 이름, 계정, 비밀번호를 입력합니다.
3. `prepare_schema.bat`를 실행합니다. 화면에 표시된 대상 DB를 확인하고 승인하면 관리 테이블 13개가 만들어집니다. 테이블이 이미 모두 있으면 도구가 그대로 종료합니다.
4. `SETRON.exe`를 다시 실행해 DB 연결 상태를 확인합니다. ‘데이터 가져오기’에서 설비현황표나 릴리즈 노트를 검토한 뒤 저장합니다.

AI 기능을 실제 서버에 연결하려면 `setron.env`의 `SETRON_AI_BASE_URL`, `SETRON_AI_API_KEY`, `SETRON_AI_MODEL`을 입력하고 앱을 다시 시작합니다. 설정 파일에는 접속 정보가 있으므로 개인 PC에 보관합니다.

## 3. 배포 폴더 구성

| 파일 | 용도 |
| --- | --- |
| `SETRON.exe` | 데스크톱 앱 |
| `prepare_schema.bat` · `SETRON_DB_SETUP.exe` | Windows에 설치한 로컬 MySQL에 관리 테이블 생성 |
| `setron.env.example` | DB·AI 접속 설정 예시 |
| `_internal/` | 실행 라이브러리, 화면 리소스, DB 스키마 |

DB에 접속하지 않고 스키마만 검사하려면 배포 폴더에서 다음 명령을 실행합니다.

```powershell
.\SETRON_DB_SETUP.exe --validate-schema
```

## 4. 소스에서 다시 빌드하기

Windows 개발 PC에 Python 3.13과 uv를 준비한 뒤 저장소 루트에서 실행합니다.

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File packaging\build_windows.ps1
```

결과는 `dist/SETRON`에 생성됩니다. 빌드는 기존 배포 폴더의 사용자 설정과 백업을 보존합니다. 다른 사람에게 배포할 때는 빈 출력 폴더에 새로 빌드해 그 결과만 압축합니다.

## 5. 설치형 MySQL 실사용 확인

S15P31B106-31, -63의 남은 확인 항목이다. 2026-11-03 개발 PC에서 공식 ZIP 버전(`mysql-5.6.19-winx64.zip`)을 콘솔로 실행해 확인했다.

| 확인 | 결과 |
| --- | --- |
| 서버 설정 | `my.ini`에 utf8mb4·utf8mb4_unicode_ci 지정 (Docker와 같음). Windows 기본 `lower_case_table_names=1`이며 테이블 이름이 모두 소문자라 영향 없음 |
| 스키마·시드 적용 | `mysql.exe`로 `schema_mysql5619.sql`, `seed_demo_catalog.sql` 실행, 테이블 13개 |
| `setron.env`로 접속 | 실행 파일이 DB 모드("MySQL DB 저장 자료")로 시작 |
| 대시보드·HeatMap 조회 | 저장 후 조회 적용 시 기준 관측일·현황 건수 반영 |
| 가져오기 저장, 같은 날 재저장 | 설비 현황·릴리즈 저장 완료, 같은 호기·기준일 재저장은 거부 |
| 저장 실패 시 전체 취소 | 실패한 저장 2번의 입력 작업이 DB에 남지 않음 |
| MySQL 통합 테스트 | `tests/*_mysql.py` 9개 파일 94개를 설치형 서버의 빈 테스트 DB에서 실행, 모두 통과 |
| SQL 내보내기 → 빈 DB 복원 | 테이블 13개 · 32행 내보내기 → 새 빈 DB에서 `mysql.exe`로 실행 → 테이블별 행 수·`CHECKSUM TABLE` 일치. 같은 DB에 다시 실행하면 첫 `CREATE TABLE`에서 멈춤 |
| HeidiSQL 9.2로 복원 | 공식 포터블 `HeidiSQL_9.2_Portable.zip`. 빈 DB를 선택하고 SQL 파일을 불러와 실행(인코딩 기본값) → 27개 문장 · 36행 · 경고 0. 한글·이모지·작은따옴표·역슬래시가 든 값까지 테이블별 행 수·`CHECKSUM TABLE`과 AUTO_INCREMENT가 원본과 일치 |
| HeidiSQL로 같은 DB에 다시 실행 | "SQL 오류 (1050): Table 'import_batch' already exists" 창(확인 버튼만 있음)을 띄우고 멈춤. 자료 변화 없음 |

받은 파일은 HeidiSQL에서 **빈 DB를 먼저 선택한 뒤** 실행하도록 안내한다. 다른 DB가 선택된 상태면 그 DB에 테이블이 만들어진다.

설치형 서버를 띄운 방법 (확인용, Windows 서비스로 등록하지 않음):

```powershell
# 압축 해제 폴더에 my.ini를 두고 콘솔로 실행. 끝낼 때는 이 창에서 Ctrl+C 또는 mysqladmin shutdown
bin\mysqld.exe --defaults-file=my.ini --console
```
