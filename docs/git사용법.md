# Git 시작 가이드

# Git 설치

해당 URL 참고: https://velog.io/@young-0320/개발-환경-설정-3-Git-설치Windows

# Git 사용법

## 1. 최초 1회 설정

Git에 본인 이름과 이메일을 등록한다. (커밋 기록에 남는 정보)

```
git config --global user.name "본인이름"
git config --global user.email "깃허브 이메일"
```

설정 확인:

```
git config --global user.name
git config --global user.email
```

---

## 2. 레포지토리 클론 (최초 1회)

작업할 폴더로 이동한 뒤 아래 명령어를 실행한다.

```bash
git clone https://github.com/young-0320/flash-margin-bench
```

클론이 완료되면 `flash-margin-bench` 폴더가 생성된다.

아래의 명령어로 작업 디렉토리로 이동한다.

```bash
cd flash-margin-bench
```

---

## 3. 작업 흐름 (매번 반복)

### 3-1. 작업 전 - 최신 코드 받기

**반드시 작업 전에 실행한다.**

```bash
git pull origin main
```

### 3-2. 작업 후 - 변경사항 올리기

```bash
git add .
git commit -m "feat: ALU 기본 연산 구현"
git push origin main
```

각 명령어 의미

- `git add .` : 변경된 파일 전체를 커밋 준비 상태로 올림
- `git commit -m "..."` : 변경사항을 저장하고 메시지 작성
- `git push origin main` : 로컬 변경사항을 GitHub에 올림

---

## 5. 현재 상태 확인

```bash
git status
```

어떤 파일이 변경됐는지 확인할 수 있다.

```bash
git log --oneline
```

커밋 히스토리를 한 줄씩 확인할 수 있다.

---

## 6. 명령어 간단하게 하기

처음 한 번만 아래 명령어를 실행하면, 이후에는 git push만 입력해도 된다.

```bash
git push -u origin main
```

이후부터는 아래처럼 간단히 사용할 수 있다.

```bash
git push
git pull
```
