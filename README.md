# JUD.M Auto Shorts v1.0

무료 운영을 전제로 한 JUD.M 게임 숏폼 자동 편집/게시 파이프라인.

## 최종 사용자 동작
운영이 연결된 뒤 사용자가 반복해서 하는 일은 하나뿐입니다.

`Google Drive > JUDM_MARKETING > 00_INBOX` 에 원본 게임 영상을 넣습니다.

그 뒤 GitHub Actions가 하루 2회(대한민국 시간 12:37 / 20:37) 자동 실행합니다.

## 처리 흐름
`00_INBOX -> 01_READY -> 자동편집 -> 플랫폼 게시 -> 02_POSTED`

- 가장 오래된 영상을 1개씩 처리합니다.
- Drive 파일의 `appProperties`에 플랫폼별 게시 ID를 저장하여 부분 성공 후 재실행해도 중복 게시하지 않습니다.
- YouTube/Instagram/TikTok 세 플랫폼을 목표로 고정합니다.
- 승인되지 않은 플랫폼은 비활성화 상태로 기다리고, 이미 성공한 플랫폼은 다시 게시하지 않습니다.
- 세 플랫폼 모두 성공하면 원본을 `02_POSTED`로 이동합니다.
- 폴더 이동 권한이 제한된 경우에도 내부 상태 마커로 중복 처리를 차단합니다.

## 자동편집
- FFmpeg + OpenCV만 사용합니다. 유료 AI 편집 API 없음.
- 화면 변화 / 움직임 / 오디오 피크를 합산해 12~24초 핵심 구간을 자동 선택합니다.
- 출력 1080x1920 / H.264 / AAC / 30fps / faststart.
- 가로 게임은 HUD가 잘리지 않도록 전체 게임 화면을 유지하고, 빈 세로 영역은 동일 영상 블러 배경으로 채웁니다.
- 첫 3.2초 강한 훅 자막.
- 초반과 하이라이트 피크에 자동 줌 펀치.
- 후반 리텐션 문구.
- 게임 파일명으로 `뿅뿅슬라임 / 피지컬넘버37 / B.Line POP / FammerWar`를 자동 구분합니다.

## 폰트
폰트 바이너리를 저장소에 넣지 않습니다.

GitHub Actions 실행 시:
- 훅: Google Fonts `Do Hyeon` (SIL OFL)
- 보조 글자: Debian `fonts-noto-cjk`의 Noto Sans CJK KR

을 무료로 설치합니다.

## 예약
`.github/workflows/judm-auto-shorts.yml`

- 12:37 Asia/Seoul
- 20:37 Asia/Seoul
- 매시 정각의 Actions 지연 가능성을 피하기 위해 37분으로 고정
- 수동 `preview` 모드로 실제 Drive 영상을 게시 없이 편집해 7일짜리 Actions artifact로 검수 가능

## 플랫폼 게이트
### YouTube
`YOUTUBE_ENABLED=false`가 기본값입니다.
자체 YouTube API 프로젝트는 compliance audit 전 공개 업로드가 제한될 수 있으므로 감사 승인 전에는 활성화하지 않습니다.

### Instagram
Instagram Login API를 사용합니다. Professional(Business/Creator) 계정용이며 `instagram_business_content_publish` 권한이 필요합니다.
Reel 게시 시 Instagram이 가져갈 공개 HTTPS URL이 필요하므로 Cloudinary 무료 계정을 임시 호스트로 사용하고, 게시 후 즉시 영상 자산을 삭제합니다.

### TikTok
Content Posting API Direct Post를 사용합니다. `video.publish` 승인 + audit 후 활성화합니다.
Access token은 24시간이므로 refresh token으로 실행 시 자동 갱신하고, GitHub Secret에 새 token pair를 다시 암호화 저장합니다.

## 보안
소스코드에는 토큰/비밀번호/클라이언트 secret을 넣지 않습니다.
모든 비밀값은 GitHub Actions Secrets만 사용합니다.

## 현재 고정 Drive Inbox
`1_a7e-874zRIyV_ojedYj0edQisGcfnUd`

`01_READY`, `02_POSTED`는 `00_INBOX`의 부모 폴더에서 이름으로 자동 검색합니다.

## 개발 검증
```bash
pip install -r requirements.txt
PYTHONPATH=src pytest -q
```

v1.0 기준 smoke test는 실제 FFmpeg로 1280x720 테스트 영상을 만들고 세 플랫폼 1080x1920 결과를 렌더링해 검증합니다.
