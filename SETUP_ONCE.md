# 1회 설정 체크리스트

이 문서는 코드 배포 후 한 번만 수행합니다. 플랫폼 승인 전에는 해당 플랫폼 변수를 `false`로 유지합니다.

## A. Drive
1. Google Cloud 프로젝트 `judm-auto-shorts`에서 Drive API 활성화.
2. 서비스 계정 1개 생성. 결제 계정 불필요.
3. 서비스 계정 JSON 키를 생성하고 전체 JSON을 GitHub Secret `GOOGLE_SERVICE_ACCOUNT_JSON`에 저장.
4. Google Drive의 `JUDM_MARKETING` 폴더를 서비스 계정 이메일에 `편집자`로 공유.
5. Actions `preview`를 한 번 실행해 실제 영상 다운로드/편집을 검증.

## B. GitHub Variables
승인된 플랫폼만 `true`로 설정:
- `YOUTUBE_ENABLED`
- `INSTAGRAM_ENABLED`
- `TIKTOK_ENABLED`

## C. YouTube (audit 승인 후)
Secrets:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`

`GOOGLE_REFRESH_TOKEN`은 `scripts/authorize_youtube.py`로 1회 생성합니다.

## D. Instagram
Secrets:
- `INSTAGRAM_USER_ID`
- `INSTAGRAM_ACCESS_TOKEN`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `GH_SECRETS_PAT` (토큰 자동 회전 저장용)

Variable:
- `INSTAGRAM_API_VERSION` (현재 앱이 지원하는 Graph API 버전)

## E. TikTok (video.publish + audit 승인 후)
Secrets:
- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_REFRESH_TOKEN`
- `TIKTOK_ACCESS_TOKEN`
- `GH_SECRETS_PAT`

메인 파이프라인은 게시 직전 refresh token을 사용해 새 access token을 얻고 새 token pair를 GitHub Secrets에 저장합니다.
