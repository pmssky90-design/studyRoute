"""StudyRoute static site generator.

The project intentionally uses only the Python standard library. The attached
Excel workbook is read directly as an OOXML zip package, so the build can run
on Windows without installing pandas, openpyxl, or any other dependency.
"""

from __future__ import annotations

import html
import hashlib
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from string import Template
from typing import Iterable
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import config


SPREADSHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELATIONSHIP_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
REGION_SUFFIX = "과외"
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
P_CLOSING_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "dl",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "ul",
}
LIST_TAGS = {"ul", "ol", "menu"}
TABLE_SECTION_TAGS = {"thead", "tbody", "tfoot"}
TABLE_CELL_TAGS = {"td", "th"}

CONTENT_SUPPLEMENTS = {
    "동성로초등과외": """
<h2>동성로초등과외 학습을 준비할 때 살펴볼 점</h2>
<p>동성로초등과외를 생각할 때는 아이가 어느 단원에서 막히는지보다 왜 그 단원에서 멈추는지를 먼저 살피는 것이 좋습니다. 초등 시기에는 계산 속도, 독해력, 문제를 끝까지 읽는 습관, 공책 정리 방식처럼 작은 요소가 학습 결과에 크게 영향을 줍니다. 동성로 주변은 이동 동선이 다양하고 방과 후 일정도 제각각이기 때문에, 아이가 지치지 않는 시간대에 복습과 예습을 나누어 배치하는 계획이 필요합니다.</p>
<p>초등학생은 아직 스스로 학습 리듬을 만들기 어렵습니다. 그래서 동성로초등과외에서는 매번 새로운 내용을 많이 넣기보다 지난 시간에 배운 개념을 짧게 확인하고, 아이가 직접 설명해 보는 과정을 두는 편이 안정적입니다. 틀린 문제를 바로 다시 풀게 하는 것보다 어떤 문장을 놓쳤는지, 계산 과정에서 어느 줄을 건너뛰었는지, 보기에서 왜 헷갈렸는지를 함께 확인하면 같은 실수를 줄이는 데 도움이 됩니다.</p>
<h3>초등 학습 습관을 만드는 방법</h3>
<p>학부모 입장에서는 점수 변화만 보기보다 공부를 시작하는 태도와 마무리 습관을 함께 보는 것이 좋습니다. 책상에 앉는 시간, 문제집을 펴는 순서, 채점 후 오답을 표시하는 방식이 일정해지면 아이는 공부를 덜 부담스럽게 받아들입니다. 동성로초등과외의 핵심은 많은 양을 빠르게 끝내는 것이 아니라, 아이가 오늘 무엇을 배웠고 내일 무엇을 다시 봐야 하는지 알게 만드는 데 있습니다.</p>
<ul>
<li>숙제는 양보다 완료 기준을 분명하게 정합니다.</li>
<li>오답은 정답만 고치지 말고 실수 원인을 짧게 적습니다.</li>
<li>읽기 문제는 밑줄 친 단어와 답의 근거를 함께 확인합니다.</li>
<li>수학 문제는 식을 쓰는 순서와 단위 표시를 반복해서 점검합니다.</li>
</ul>
<p>학교 생활과 연결해서 보는 것도 중요합니다. 수업 시간에 발표를 어려워하는 아이는 알고 있는 내용도 문제 앞에서 망설일 수 있고, 글씨가 느린 아이는 풀이 시간이 부족해질 수 있습니다. 이런 경우에는 단순히 더 어려운 문제를 주기보다 쉬운 문제를 정확하게 설명하는 연습부터 시작하는 편이 좋습니다. 동성로초등과외를 통해 아이가 자신의 풀이를 말로 정리하면 개념 이해와 자신감이 함께 쌓입니다.</p>
<h3>복습과 시험 준비</h3>
<p>초등 시험 준비는 벼락치기보다 짧은 반복이 효과적입니다. 단원평가나 수행평가 전에는 교과서 핵심 문장, 선생님이 강조한 활동, 자주 틀린 유형을 순서대로 확인합니다. 특히 국어와 사회, 과학은 내용을 외우기 전에 질문을 읽고 답의 근거를 찾는 연습이 필요합니다. 동성로초등과외에서는 이런 과정을 주간 계획 안에 넣어 아이가 시험을 특별한 부담이 아니라 평소 학습의 연장으로 받아들이게 하는 것이 좋습니다.</p>
<p>마무리 단계에서는 아이가 스스로 다음 공부를 예측하도록 돕습니다. 오늘 틀린 문제가 무엇인지, 다시 풀 때 조심할 부분이 무엇인지, 학교 수업에서 질문하고 싶은 내용이 무엇인지 짧게 정리하면 다음 학습의 출발점이 분명해집니다. 동성로초등과외는 아이의 현재 수준을 존중하면서도 작은 습관을 꾸준히 쌓아 가는 방향으로 운영될 때 가장 안정적인 효과를 기대할 수 있습니다.</p>
""",
    "산격동과외": """
<h2>산격동과외를 계획할 때 필요한 학습 점검</h2>
<p>산격동과외는 학생의 현재 성적만 보고 시작하기보다 생활 리듬과 공부 습관을 함께 살피는 과정이 중요합니다. 같은 산격동 안에서도 학교 일정, 학원 이동 시간, 가정에서 공부할 수 있는 시간은 학생마다 다릅니다. 그래서 먼저 평일과 주말의 학습 가능 시간을 나누고, 실제로 집중할 수 있는 시간을 기준으로 계획을 세워야 합니다. 무리하게 시간을 늘리기보다 꾸준히 지킬 수 있는 루틴을 만드는 것이 우선입니다.</p>
<p>학생이 과목별로 어려움을 느끼는 이유는 다양합니다. 개념을 모르는 경우도 있지만, 문제를 급하게 읽거나 풀이 과정을 생략하거나 오답을 다시 보지 않는 습관 때문에 점수가 흔들리기도 합니다. 산격동과외를 진행할 때는 틀린 문제의 정답을 확인하는 데서 멈추지 않고, 실수의 원인을 문장으로 남기는 방식이 도움이 됩니다. 이 기록이 쌓이면 시험 전 복습 자료로도 활용할 수 있습니다.</p>
<h3>지역과 학교 생활을 고려한 공부 방법</h3>
<p>산격동은 생활권 안에서 이동 동선이 비교적 다양하기 때문에 학생이 피곤한 시간대를 피하는 것도 중요합니다. 특히 중고등학생은 학교 수업, 수행평가, 동아리 활동, 시험 기간이 겹치면 공부 계획이 쉽게 밀립니다. 이럴 때 산격동과외는 하루 단위 계획보다 주간 단위 계획으로 운영하는 편이 안정적입니다. 중요한 과제와 시험 범위를 먼저 적고, 남는 시간에 문제 풀이와 복습을 배치하면 부담을 줄일 수 있습니다.</p>
<ul>
<li>학교 진도와 개인 약점을 따로 기록합니다.</li>
<li>오답은 계산 실수, 개념 부족, 독해 실수로 나누어 봅니다.</li>
<li>시험 2주 전에는 새 문제보다 누적 오답을 먼저 확인합니다.</li>
<li>공부 시간이 짧은 날에는 핵심 개념 하나와 대표 문제 몇 개에 집중합니다.</li>
</ul>
<p>학부모 관점에서는 학생이 실제로 이해했는지 확인하는 질문이 필요합니다. “다 했니”보다 “오늘 다시 설명할 수 있는 내용이 뭐니”처럼 구체적으로 물으면 학생도 자신의 학습 상태를 돌아보기 쉽습니다. 산격동과외의 역할은 단순히 문제 수를 늘리는 것이 아니라 학생이 스스로 부족한 부분을 발견하고 다음 공부를 준비하도록 돕는 데 있습니다.</p>
<h3>시간 관리와 오답 관리</h3>
<p>시간 관리는 공부를 오래 하는 것과 다릅니다. 한 시간 동안 무엇을 끝낼지, 끝난 뒤 무엇을 확인할지 정해야 실제 학습량이 보입니다. 산격동과외에서는 짧은 목표를 세우고 완료 후 바로 점검하는 방식이 효과적입니다. 예를 들어 수학은 개념 확인, 대표 유형, 오답 정리 순서로 나누고, 영어는 단어, 문장 해석, 지문 근거 찾기 순서로 나누면 과목별 흐름이 분명해집니다.</p>
<p>마지막으로 복습은 시험 직전에만 하는 일이 아닙니다. 하루 뒤, 일주일 뒤, 시험 전처럼 간격을 두고 같은 내용을 다시 보면 기억이 오래 유지됩니다. 산격동과외를 통해 학생이 자신의 오답 노트를 직접 설명하고, 비슷한 유형을 다시 풀어 보며, 다음 시험에서 조심할 부분을 정리한다면 학습의 방향이 더 선명해집니다. 이런 과정이 쌓이면 성적뿐 아니라 공부를 대하는 태도도 안정됩니다.</p>
""",
    "신서동초등과외": """
<h2>신서동초등과외에서 중요한 기본 학습 습관</h2>
<p>신서동초등과외를 준비할 때는 아이가 어떤 과목을 어려워하는지와 함께 공부를 어떻게 시작하고 끝내는지를 살펴야 합니다. 초등학생은 아직 학습 습관이 완성되지 않았기 때문에 한 번에 많은 내용을 넣기보다, 매일 비슷한 순서로 공부를 진행하는 것이 안정적입니다. 예습, 학교 수업, 복습이 서로 연결되면 아이는 낯선 단원도 덜 불안하게 받아들입니다.</p>
<p>신서동 주변의 초등학생들은 학교 일정과 방과 후 활동, 가정 학습 시간이 서로 다를 수 있습니다. 그래서 신서동초등과외에서는 아이가 집중하기 좋은 시간대를 찾는 것부터 시작하는 편이 좋습니다. 피곤한 시간에 어려운 문제를 많이 풀리면 학습에 대한 부담이 커질 수 있습니다. 짧더라도 정확하게 읽고, 풀고, 설명하는 시간이 반복될 때 공부 습관이 자연스럽게 자리 잡습니다.</p>
<h3>읽기와 계산 실수를 줄이는 과정</h3>
<p>초등 과정에서 자주 보이는 어려움은 개념 부족보다 문제를 끝까지 읽지 않는 습관에서 시작되기도 합니다. 국어 문제에서는 질문의 조건을 놓치고, 수학 문제에서는 단위를 빠뜨리거나 계산 줄을 건너뛰는 경우가 있습니다. 신서동초등과외는 이런 실수를 단순한 부주의로 넘기지 않고, 아이가 어떤 상황에서 자주 틀리는지 기록하는 과정이 필요합니다.</p>
<ul>
<li>문제를 읽을 때 조건과 묻는 말을 나누어 표시합니다.</li>
<li>계산 과정은 한 줄씩 쓰고 중간 값을 지우지 않습니다.</li>
<li>오답은 다시 풀기 전에 틀린 이유를 먼저 말해 봅니다.</li>
<li>복습은 긴 시간보다 짧은 반복으로 진행합니다.</li>
</ul>
<p>학부모가 확인할 부분도 있습니다. 아이가 숙제를 끝냈는지보다 어떤 문제를 어려워했는지, 다시 설명할 수 있는지, 다음 시간에 무엇을 확인해야 하는지를 보는 것이 좋습니다. 신서동초등과외에서는 아이가 스스로 “오늘 배운 것”과 “다시 볼 것”을 구분할 수 있도록 돕는 과정이 중요합니다. 이 습관은 학년이 올라갈수록 더 큰 차이를 만듭니다.</p>
<h3>학교 생활과 시험 준비</h3>
<p>초등 시험 준비는 단순 암기보다 학교 수업에서 다룬 활동과 교과서 핵심 내용을 연결하는 방식이 효과적입니다. 수행평가가 있는 단원은 결과물만 보는 것이 아니라 준비 과정, 발표 내용, 정리 문장을 함께 살펴야 합니다. 신서동초등과외를 통해 아이가 배운 내용을 자기 말로 설명하면 시험 문제를 만났을 때도 당황하지 않고 근거를 찾을 수 있습니다.</p>
<p>마무리 복습에서는 쉬운 문제를 정확히 푸는 경험이 필요합니다. 어려운 문제를 많이 푸는 것보다 기본 문제에서 실수를 줄이는 것이 초등 학습의 토대가 됩니다. 신서동초등과외는 아이의 속도를 존중하면서도 꾸준한 복습, 오답 관리, 시간 관리가 이어지도록 계획할 때 효과적입니다. 작은 성공 경험이 쌓이면 아이는 공부를 해야 하는 일로만 느끼지 않고, 스스로 해낼 수 있는 과정으로 받아들이게 됩니다.</p>
""",
    "이시아폴리스과외": """
<h2>이시아폴리스과외를 시작하기 전 확인할 학습 흐름</h2>
<p>이시아폴리스과외는 학생의 과목별 약점뿐 아니라 생활권과 이동 시간, 학교 일정까지 함께 고려할 때 더 안정적으로 운영될 수 있습니다. 학생마다 집중이 잘되는 시간과 피로가 쌓이는 시간이 다르기 때문에, 먼저 하루 공부 가능 시간을 현실적으로 확인하는 것이 필요합니다. 계획은 길게 세우기보다 지킬 수 있는 단위로 나누고, 완료 후 바로 확인하는 방식이 좋습니다.</p>
<p>학습이 부족해 보일 때 무조건 문제 수를 늘리는 방식은 오래가기 어렵습니다. 학생이 개념을 모르는지, 문제를 잘못 읽는지, 풀이 과정을 생략하는지, 시험 시간에 긴장하는지를 구분해야 합니다. 이시아폴리스과외에서는 같은 오답이라도 원인을 다르게 기록하는 것이 중요합니다. 원인을 나누어 보면 다음 학습에서 무엇을 줄이고 무엇을 반복해야 하는지 분명해집니다.</p>
<h3>공부 습관과 시간 관리</h3>
<p>이시아폴리스 지역의 학생들은 학교 수업과 방과 후 일정, 가정 학습 시간이 겹치면서 계획이 밀리는 경우가 있습니다. 이런 상황에서는 매일 같은 양을 요구하기보다 주간 목표를 세우고, 바쁜 날에는 핵심 복습만 남기는 방식이 현실적입니다. 이시아폴리스과외는 학생이 지치지 않으면서도 학습의 흐름을 놓치지 않도록 조절하는 과정이 중요합니다.</p>
<ul>
<li>학교 진도와 개인 약점을 분리해서 기록합니다.</li>
<li>오답은 개념, 계산, 독해, 시간 부족으로 나누어 정리합니다.</li>
<li>시험 전에는 새 문제보다 반복해서 틀린 문제를 먼저 확인합니다.</li>
<li>복습은 하루 뒤와 일주일 뒤에 다시 보는 방식으로 계획합니다.</li>
</ul>
<p>학부모 입장에서는 학생이 책상에 앉아 있는 시간보다 실제로 이해한 내용을 보는 것이 좋습니다. 오늘 배운 개념을 설명할 수 있는지, 틀린 문제를 다시 풀 때 같은 실수를 줄였는지, 다음 수업에서 확인할 질문이 있는지를 살피면 학습 상태를 더 정확히 알 수 있습니다. 이시아폴리스과외는 이런 점검 과정을 통해 학생이 자신의 공부를 스스로 관리하도록 돕는 방향이 좋습니다.</p>
<h3>시험 준비와 복습 방법</h3>
<p>시험 준비는 범위를 모두 훑는 것에서 끝나지 않습니다. 자주 틀리는 유형, 학교 수업에서 강조한 내용, 수행평가와 연결되는 단원을 따로 정리해야 합니다. 수학은 풀이 과정을 남기는 습관이 중요하고, 영어는 문장 해석과 지문 근거 찾기를 함께 연습해야 합니다. 이시아폴리스과외에서는 시험 기간 전에 이런 과정을 미리 나누어 두면 막판 부담을 줄일 수 있습니다.</p>
<p>마지막으로 공부의 흐름은 작은 반복에서 만들어집니다. 하루 공부가 완벽하지 않아도 무엇을 했고 무엇을 다시 봐야 하는지 기록하면 다음 학습이 쉬워집니다. 이시아폴리스과외를 통해 학생이 자기 실수의 원인을 알고, 필요한 복습을 선택하며, 학교 생활과 시험 준비를 균형 있게 이어 간다면 학습 태도도 점차 안정될 수 있습니다.</p>
""",
}

CONTENT_SUPPLEMENTS_EXTRA = {
    "봉명동초등수학과외": """
<h2>봉명동초등수학과외에서 살펴볼 수학 습관</h2>
<p>봉명동초등수학과외는 계산을 많이 시키는 것보다 아이가 문제를 어떻게 읽고 식을 어떻게 세우는지 확인하는 과정이 중요합니다. 초등 수학은 단원마다 새 공식이 늘어나는 것처럼 보이지만, 실제로는 수 개념, 단위, 도형 감각, 문장제 독해가 서로 연결되어 있습니다. 봉명동초등수학과외를 진행할 때 아이가 어느 부분에서 멈추는지 차분히 확인하면 불필요한 반복을 줄일 수 있습니다.</p>
<h3>오답을 줄이는 복습 방식</h3>
<p>문제를 틀렸을 때 바로 정답을 알려 주기보다 아이가 처음 세운 식을 다시 보게 하는 편이 좋습니다. 계산 실수인지, 조건을 빠뜨린 것인지, 문제의 뜻을 잘못 이해한 것인지에 따라 복습 방법이 달라집니다. 봉명동초등수학과외에서는 오답 옆에 짧은 이유를 적고, 비슷한 문제를 한두 개 더 풀어 보는 방식이 도움이 됩니다.</p>
<ul>
<li>문장제는 묻는 말과 주어진 조건을 나누어 표시합니다.</li>
<li>도형 문제는 그림에 길이와 단위를 직접 써 봅니다.</li>
<li>계산 문제는 중간 과정을 지우지 않고 남겨 둡니다.</li>
<li>복습은 하루 뒤에 같은 유형을 다시 확인합니다.</li>
</ul>
<p>학부모는 결과보다 과정의 변화를 보는 것이 좋습니다. 아이가 풀이를 말로 설명할 수 있고, 틀린 이유를 스스로 찾기 시작하면 다음 단원으로 넘어갈 준비가 된 것입니다. 봉명동초등수학과외는 이런 작은 습관을 꾸준히 쌓아 수학에 대한 부담을 줄이는 방향으로 이어질 때 안정적입니다.</p>
""",
    "태전동초등수학과외": """
<h2>태전동초등수학과외의 기본 방향</h2>
<p>태전동초등수학과외는 아이가 수학을 어렵게 느끼는 이유를 세밀하게 나누어 보는 데서 시작할 수 있습니다. 계산은 빠르지만 문장제를 어려워하는 아이도 있고, 개념은 이해했지만 풀이를 정리하지 못해 실수하는 아이도 있습니다. 태전동초등수학과외에서는 문제를 많이 푸는 것만큼 풀이 과정을 남기고 다시 설명하는 습관이 중요합니다.</p>
<h3>문장제와 계산 실수 관리</h3>
<p>초등 수학에서 문장제는 국어 독해와도 연결됩니다. 문제를 끝까지 읽고 무엇을 구해야 하는지 표시하는 연습이 필요합니다. 계산 과정에서는 받아올림, 단위, 괄호, 나눗셈 몫과 나머지처럼 자주 놓치는 부분을 따로 확인하면 좋습니다. 태전동초등수학과외는 이런 반복 실수를 기록해 다음 복습의 기준으로 삼는 방식이 효과적입니다.</p>
<ul>
<li>풀이 전에는 문제의 조건을 먼저 표시합니다.</li>
<li>풀이 후에는 답의 단위가 맞는지 확인합니다.</li>
<li>오답은 정답보다 틀린 이유를 먼저 적습니다.</li>
<li>시험 전에는 새 문제보다 누적 오답을 다시 풉니다.</li>
</ul>
<p>아이의 자신감은 어려운 문제를 갑자기 맞히는 것보다 기본 문제를 안정적으로 해결하는 경험에서 생깁니다. 태전동초등수학과외는 학교 진도와 아이의 이해 속도를 함께 보면서, 무리한 선행보다 탄탄한 복습과 설명 연습을 이어 가는 방향이 좋습니다.</p>
""",
    "테크노폴리스초등수학과외": """
<h2>테크노폴리스초등수학과외 학습 계획</h2>
<p>테크노폴리스초등수학과외는 아이의 생활 리듬과 학교 진도를 함께 고려해 계획하는 것이 좋습니다. 초등 수학은 단원별 난도가 갑자기 달라지기보다 이전 학년의 개념이 다음 단원에서 다시 쓰이는 경우가 많습니다. 그래서 현재 단원만 급하게 따라가기보다 지난 개념 중 약한 부분을 짧게 확인하는 시간이 필요합니다.</p>
<h3>풀이 과정을 남기는 습관</h3>
<p>수학을 잘하는 아이도 풀이 과정을 생략하면 실수가 반복될 수 있습니다. 테크노폴리스초등수학과외에서는 답을 맞혔는지보다 어떤 순서로 생각했는지 확인하는 과정이 중요합니다. 특히 분수, 소수, 도형, 비와 비율처럼 개념이 이어지는 단원은 아이가 자기 말로 설명할 수 있어야 다음 학습이 안정됩니다.</p>
<ul>
<li>개념 확인 후 대표 문제를 풀고 바로 설명합니다.</li>
<li>틀린 문제는 같은 날 다시 풀고 일주일 뒤 재확인합니다.</li>
<li>문장제는 식을 세우기 전 상황을 짧게 정리합니다.</li>
<li>도형 문제는 그림에 조건을 직접 표시합니다.</li>
</ul>
<p>학부모가 볼 때는 문제집 진도보다 아이가 실수를 줄이는 과정을 확인하는 것이 좋습니다. 테크노폴리스초등수학과외는 규칙적인 복습, 오답 원인 기록, 학교 수업과의 연결을 통해 아이가 수학을 차분히 받아들이도록 돕는 방향이 적절합니다.</p>
""",
    "대덕구초등영어과외": """
<h2>대덕구초등영어과외에서 필요한 영어 학습 습관</h2>
<p>대덕구초등영어과외는 단어를 많이 외우는 것만으로 충분하지 않습니다. 초등 영어에서는 소리, 단어, 문장, 짧은 글 읽기가 자연스럽게 이어져야 합니다. 아이가 영어를 부담스럽게 느낀다면 먼저 듣고 따라 말하는 과정에서 막히는지, 단어 뜻을 기억하지 못하는지, 문장 순서를 헷갈리는지 살피는 것이 좋습니다.</p>
<h3>단어와 문장을 연결하는 방법</h3>
<p>단어 암기는 뜻만 외우는 방식보다 짧은 문장 안에서 반복하는 편이 효과적입니다. 대덕구초등영어과외에서는 오늘 배운 단어를 문장으로 읽고, 그림이나 상황과 연결해 말해 보는 연습이 도움이 됩니다. 문장을 쓸 때는 철자 실수와 대문자, 마침표처럼 작은 요소도 함께 확인해야 합니다.</p>
<ul>
<li>새 단어는 소리, 뜻, 예문 순서로 확인합니다.</li>
<li>짧은 문장은 크게 읽고 뜻을 말해 봅니다.</li>
<li>틀린 철자는 같은 단어를 문장 안에서 다시 씁니다.</li>
<li>읽기 지문은 답의 근거가 되는 문장을 표시합니다.</li>
</ul>
<p>학부모는 아이가 영어를 얼마나 오래 했는지보다 스스로 읽고 이해한 내용을 말할 수 있는지 확인하면 좋습니다. 대덕구초등영어과외는 학교 영어와 생활 속 표현을 연결하면서, 아이가 영어 문장을 두려워하지 않도록 작은 성공 경험을 쌓는 방향으로 진행될 때 안정적입니다.</p>
""",
    "산격동과외": """
<h2>산격동과외의 마무리 점검</h2>
<p>산격동과외를 꾸준히 이어 가려면 학습 결과를 한 번에 판단하기보다 변화의 흐름을 보는 태도가 필요합니다. 처음에는 공부 시간을 지키는 것만으로도 의미가 있고, 이후에는 오답을 줄이는 과정과 시험 전 복습의 정확도를 함께 살필 수 있습니다. 학생이 스스로 부족한 부분을 말하기 시작하면 학습 계획도 더 현실적으로 조정할 수 있습니다.</p>
<p>또한 과목별 계획은 서로 분리되어야 합니다. 수학은 개념과 풀이 과정, 영어는 단어와 문장 해석, 국어는 지문 근거 찾기처럼 확인해야 할 지점이 다릅니다. 산격동과외는 이런 차이를 반영해 학생에게 맞는 복습 순서를 만들고, 학교 생활과 시험 준비가 무리 없이 이어지도록 돕는 방향이 좋습니다.</p>
""",
    "이시아폴리스과외": """
<h2>이시아폴리스과외의 지속적인 복습 기준</h2>
<p>이시아폴리스과외를 통해 학습을 이어 갈 때는 매주 같은 기준으로 점검하는 습관이 필요합니다. 이번 주에 이해한 개념, 아직 불안한 유형, 시험 전 다시 볼 오답을 나누어 기록하면 다음 공부의 우선순위가 분명해집니다. 학생이 스스로 계획을 확인하면 공부가 막연한 부담이 아니라 관리할 수 있는 과정으로 바뀝니다.</p>
<p>학습 습관은 짧은 반복에서 만들어집니다. 하루 공부가 길지 않아도 정해진 시간에 시작하고, 끝난 뒤 오답과 복습 내용을 정리하면 누적 효과가 생깁니다. 이시아폴리스과외는 학생의 생활 리듬을 해치지 않으면서 학교 진도와 개인 약점을 함께 보완하는 방식으로 이어질 때 안정적인 학습 흐름을 만들 수 있습니다.</p>
""",
}


@dataclass(frozen=True)
class WorkbookRow:
    """One keyword/body record from the Excel workbook."""

    sheet_name: str
    keyword: str
    body_html: str


@dataclass(frozen=True)
class BreadcrumbItem:
    """One visible breadcrumb item."""

    label: str
    url: str


@dataclass(frozen=True)
class LinkItem:
    """A validated internal link."""

    label: str
    url: str


@dataclass(frozen=True)
class LinkSection:
    """A titled group of related internal links."""

    title: str
    links: tuple[LinkItem, ...]


@dataclass(frozen=True)
class Page:
    """A renderable static page."""

    output_path: str
    template: str
    title: str
    description: str
    keyword: str = ""
    body_html: str = ""
    breadcrumbs: tuple[BreadcrumbItem, ...] = field(default_factory=tuple)
    link_sections: tuple[LinkSection, ...] = field(default_factory=tuple)
    body_class: str = "page"
    canonical_path: str | None = None
    extra_context: dict[str, str] = field(default_factory=dict)

    @property
    def url_path(self) -> str:
        if self.canonical_path is not None:
            return self.canonical_path
        if self.output_path == "index.html":
            return "/"
        return "/" + self.output_path.replace("\\", "/").removesuffix("index.html")


class TemplateRenderer:
    """Loads templates and replaces `${name}` placeholders with context values."""

    def __init__(self, template_dir: Path) -> None:
        self.template_dir = template_dir
        self._cache: dict[str, str] = {}

    def render(self, template_name: str, context: dict[str, str]) -> str:
        template_text = self._load(template_name)
        return Template(template_text).safe_substitute(context)

    def partial(self, name: str, context: dict[str, str]) -> str:
        return self.render(f"partials/{name}.html", context)

    def _load(self, template_name: str) -> str:
        if template_name not in self._cache:
            path = self.template_dir / template_name
            self._cache[template_name] = path.read_text(encoding="utf-8")
        return self._cache[template_name]


class HTMLFragmentNormalizer(HTMLParser):
    """Repair malformed HTML fragments without changing text nodes.

    The workbook body column sometimes contains unclosed or misnested tags.
    This normalizer mirrors browser-style recovery for common content tags so
    the final generated page has a stable, valid outer DOM.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.output: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._prepare_for_start(tag)
        self.output.append(self._format_start_tag(tag, attrs))
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._prepare_for_start(tag)
        if tag in VOID_TAGS:
            self.output.append(self._format_start_tag(tag, attrs))
        else:
            self.output.append(self._format_start_tag(tag, attrs))
            self.output.append(f"</{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in self.stack:
            return
        while self.stack:
            open_tag = self.stack.pop()
            self.output.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        self.output.append(data)

    def handle_entityref(self, name: str) -> None:
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.output.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.output.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        # Document declarations are stripped before fragment normalization.
        return

    def close(self) -> None:
        super().close()
        while self.stack:
            self.output.append(f"</{self.stack.pop()}>")

    def html(self) -> str:
        return "".join(self.output)

    def _prepare_for_start(self, tag: str) -> None:
        if tag in P_CLOSING_TAGS and self._is_open("p"):
            self._close_until("p")

        if tag == "li":
            self._close_open_list_item()
            if not any(open_tag in LIST_TAGS for open_tag in reversed(self.stack)):
                self.output.append("<ul>")
                self.stack.append("ul")

        if tag in TABLE_SECTION_TAGS:
            self._close_open_table_cell()
            self._close_open_row()
            if not self._is_open("table"):
                self.output.append("<table>")
                self.stack.append("table")

        if tag == "tr":
            self._close_open_table_cell()
            self._close_open_row()
            if not self._is_open("table"):
                self.output.append("<table>")
                self.stack.append("table")

        if tag in TABLE_CELL_TAGS:
            self._close_open_table_cell()
            if not self._is_open("tr"):
                if not self._is_open("table"):
                    self.output.append("<table>")
                    self.stack.append("table")
                self.output.append("<tr>")
                self.stack.append("tr")

    def _format_start_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        rendered_attrs = []
        for name, value in attrs:
            if value is None:
                rendered_attrs.append(html.escape(name, quote=True))
            else:
                rendered_attrs.append(f'{html.escape(name, quote=True)}="{html.escape(value, quote=True)}"')
        suffix = (" " + " ".join(rendered_attrs)) if rendered_attrs else ""
        return f"<{tag}{suffix}>"

    def _is_open(self, tag: str) -> bool:
        return tag in self.stack

    def _close_until(self, tag: str) -> None:
        while self.stack:
            open_tag = self.stack.pop()
            self.output.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def _close_open_list_item(self) -> None:
        if self.stack and self.stack[-1] == "li":
            self.output.append("</li>")
            self.stack.pop()

    def _close_open_table_cell(self) -> None:
        if self.stack and self.stack[-1] in TABLE_CELL_TAGS:
            self.output.append(f"</{self.stack.pop()}>")

    def _close_open_row(self) -> None:
        if self.stack and self.stack[-1] == "tr":
            self.output.append("</tr>")
            self.stack.pop()


def clean_output() -> None:
    """Reset the output directory before every build."""

    if config.OUTPUT_DIR.exists():
        for attempt in range(5):
            try:
                shutil.rmtree(config.OUTPUT_DIR)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.5)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def ensure_source_directories() -> None:
    """Create required source directories if they are missing."""

    for directory in [
        config.TEMPLATE_DIR,
        config.TEMPLATE_DIR / "pages",
        config.TEMPLATE_DIR / "partials",
        config.ASSET_DIR / "css",
        config.ASSET_DIR / "js",
        config.ASSET_DIR / "images",
        config.DATA_DIR,
        config.ROOT_DIR / "scripts",
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def copy_assets() -> None:
    """Copy static assets into the deployable output folder."""

    target = config.OUTPUT_DIR / "assets"
    if target.exists():
        shutil.rmtree(target)
    if config.ASSET_DIR.exists():
        shutil.copytree(config.ASSET_DIR, target, copy_function=shutil.copy)
    root_favicon = target / "images" / "favicon.ico"
    if root_favicon.exists():
        shutil.copy(root_favicon, config.OUTPUT_DIR / "favicon.ico")


def find_workbook() -> Path:
    """Return the first workbook in data/ unless a config path is provided."""

    if config.SOURCE_WORKBOOK.exists():
        return config.SOURCE_WORKBOOK

    workbooks = sorted(config.DATA_DIR.glob("*.xlsx"))
    if not workbooks:
        raise FileNotFoundError("data 폴더에서 .xlsx 입력 파일을 찾을 수 없습니다.")
    return workbooks[0]


def read_workbook_rows(workbook_path: Path) -> list[WorkbookRow]:
    """Read every sheet's A/B columns from an xlsx file without external libs."""

    rows: list[WorkbookRow] = []
    with zipfile.ZipFile(workbook_path) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}
        shared_strings = read_shared_strings(archive)

        for sheet in workbook_xml.find("a:sheets", SPREADSHEET_NS):
            sheet_name = sheet.attrib["name"].strip()
            target = rel_map[sheet.attrib[RELATIONSHIP_ID]].lstrip("/")
            sheet_path = "xl/" + target if not target.startswith("xl/") else target
            sheet_xml = ET.fromstring(archive.read(sheet_path))

            for keyword, body_html in read_sheet_rows(sheet_xml, shared_strings):
                if keyword == "키워드":
                    continue
                rows.append(
                    WorkbookRow(
                        sheet_name=sheet_name,
                        keyword=keyword,
                        body_html=body_html,
                    )
                )

    return rows


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Read Excel shared strings, including simple rich-text runs."""

    try:
        xml_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    strings: list[str] = []
    for item in xml_root.findall("a:si", SPREADSHEET_NS):
        strings.append("".join(node.text or "" for node in item.findall(".//a:t", SPREADSHEET_NS)))
    return strings


def read_sheet_rows(sheet_xml: ET.Element, shared_strings: list[str]) -> Iterable[tuple[str, str]]:
    """Yield keyword/body pairs from columns A and B."""

    for row in sheet_xml.findall(".//a:sheetData/a:row", SPREADSHEET_NS):
        cells: dict[str, str] = {}
        for cell in row.findall("a:c", SPREADSHEET_NS):
            column = re.sub(r"\d+", "", cell.attrib.get("r", ""))
            if column in {"A", "B"}:
                cells[column] = read_cell_value(cell, shared_strings)

        keyword = cells.get("A", "").strip()
        if keyword:
            rows_body = cells.get("B", "")
            yield keyword, rows_body


def extract_body_fragment(body_html: str) -> str:
    """Return renderable body content while preserving the visible body HTML.

    Some workbook cells contain a complete HTML document. Nesting doctype,
    html, head, title, and body tags inside the generated article breaks the
    outer page. When a body element exists, only its inner HTML is inserted.
    Fragment-style cells are returned unchanged except for document wrapper
    tags that cannot legally appear inside the article body.
    """

    body_match = re.search(r"(?is)<body\b[^>]*>(.*?)</body>", body_html)
    if body_match:
        return normalize_html_fragment(body_match.group(1).strip())

    cleaned = re.sub(r"(?is)<!doctype[^>]*>", "", body_html)
    cleaned = re.sub(r"(?is)<head\b[^>]*>.*?</head>", "", cleaned)
    cleaned = re.sub(r"(?is)</?html\b[^>]*>", "", cleaned)
    cleaned = re.sub(r"(?is)</?body\b[^>]*>", "", cleaned)
    return normalize_html_fragment(cleaned)


def normalize_html_fragment(fragment: str) -> str:
    """Normalize tag structure while preserving text content and order."""

    parser = HTMLFragmentNormalizer()
    parser.feed(fragment)
    parser.close()
    return parser.html()


def supplement_short_content(keyword: str, body_html: str) -> str:
    """Append keyword-specific content only for pages known to be too short."""

    supplements = [
        supplement
        for supplement in [
            CONTENT_SUPPLEMENTS.get(keyword),
            CONTENT_SUPPLEMENTS_EXTRA.get(keyword),
        ]
        if supplement
    ]
    if not supplements:
        return body_html
    return body_html + "\n" + "\n".join(normalize_html_fragment(supplement.strip()) for supplement in supplements)


def body_has_keyword_h1(body_html: str, keyword: str) -> bool:
    """Return True when the source body already contains the required H1."""

    for match in re.findall(r"(?is)<h1\b[^>]*>(.*?)</h1>", body_html):
        text = re.sub(r"(?is)<[^>]+>", "", match)
        text = re.sub(r"\s+", " ", html.unescape(text)).strip()
        if text == keyword:
            return True
    return False


def read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    """Return the display value of a spreadsheet cell."""

    inline = cell.find("a:is", SPREADSHEET_NS)
    if inline is not None:
        return "".join(node.text or "" for node in inline.findall(".//a:t", SPREADSHEET_NS))

    value = cell.find("a:v", SPREADSHEET_NS)
    if value is None:
        return ""

    text = value.text or ""
    if cell.attrib.get("t") == "s":
        return shared_strings[int(text)]
    return text


def slug_to_output_path(slug: str) -> str:
    """Build an output path from the exact A-column keyword."""

    return f"{slug}/index.html"


def slug_to_relative_url(slug: str) -> str:
    """Build a browser-safe relative URL for internal links."""

    return f"{quote(slug)}/"


def slug_to_canonical_path(slug: str) -> str:
    """Build a root URL path for canonical and sitemap entries."""

    return f"/{quote(slug)}/"


def absolute_url(path: str) -> str:
    """Build an absolute URL from a site path."""

    return urljoin(config.BASE_URL.rstrip("/") + "/", path.lstrip("/"))


def root_asset_path(path: str) -> str:
    """Convert an asset path to a site-root path for canonical metadata."""

    clean_path = path.split("?", 1)[0].lstrip("/")
    return "/" + clean_path


def output_relative_prefix(output_path: str) -> str:
    """Return the relative prefix from an output HTML file to output root."""

    parent = Path(output_path.replace("\\", "/")).parent
    if str(parent) == ".":
        return ""
    return "../" * len(parent.parts)


def relative_asset_path(path: str, asset_prefix: str) -> str:
    """Return a file:// friendly asset path relative to the current HTML file."""

    return asset_prefix + path.split("?", 1)[0].lstrip("/")


def html_attr(value: str) -> str:
    """Escape a string for safe use in HTML text or attributes."""

    return html.escape(value, quote=True)


def select_og_image_path(page: Page) -> str:
    """Select a stable search thumbnail without using the body image."""

    if page.output_path == "index.html" or not page.keyword:
        return config.DEFAULT_IMAGE

    digest = hashlib.sha256(page.keyword.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % len(config.OG_THUMBNAILS)
    return config.OG_THUMBNAILS[index]


def render_body_image(keyword: str, asset_prefix: str) -> str:
    """Render the shared body image that appears immediately after H1."""

    alt = html_attr(f"{keyword} 학습 정보")
    return (
        '<figure class="body-common-image">\n'
        f'  <img src="{relative_asset_path(config.BODY_IMAGE_PATH, asset_prefix)}" alt="{alt}" '
        'loading="eager" decoding="async" fetchpriority="high" '
        f'width="{config.BODY_IMAGE_WIDTH}" height="{config.BODY_IMAGE_HEIGHT}">\n'
        "</figure>"
    )


def insert_body_image_after_first_h1(body_html: str, image_html: str) -> str:
    """Place the shared body image after a source-provided H1."""

    return re.sub(r"(?is)(</h1>)", rf"\1\n{image_html}", body_html, count=1)


def strip_leading_h1_and_body_image(body_html: str, keyword: str) -> str:
    """Remove technical leading H1/image so the template controls page layout."""

    h1_pattern = rf"(?is)^\s*<h1\b[^>]*>\s*{re.escape(keyword)}\s*</h1>\s*"
    cleaned = re.sub(h1_pattern, "", body_html, count=1)
    image_pattern = r"(?is)^\s*<figure\b[^>]*class=\"[^\"]*\bbody-common-image\b[^\"]*\"[^>]*>.*?</figure>\s*"
    return re.sub(image_pattern, "", cleaned, count=1)


def render_navigation(items: Iterable[dict[str, str]], prefix: str = "") -> str:
    links = []
    for item in items:
        label = html_attr(item["label"])
        url = item["url"]
        if url.startswith("#"):
            rendered_url = url
        elif url.startswith("./"):
            rendered_url = prefix or "./"
        else:
            rendered_url = prefix + url
        url = html_attr(rendered_url)
        links.append(f'<a class="nav-link" href="{url}">{label}</a>')
    return "\n          ".join(links)


def render_breadcrumbs(page: Page) -> str:
    items = page.breadcrumbs or (BreadcrumbItem("홈", "./"),)
    parts = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        label = html_attr(item.label)
        if index == total:
            parts.append(f'<li aria-current="page">{label}</li>')
        else:
            parts.append(f'<li><a href="{html_attr(item.url)}">{label}</a></li>')
    return "\n          ".join(parts)


def render_link_list(links: Iterable[LinkItem]) -> str:
    items = []
    for link in links:
        items.append(f'<li><a href="{html_attr(link.url)}">{html_attr(link.label)}</a></li>')
    return "\n              ".join(items)


def render_link_sections(sections: Iterable[LinkSection]) -> str:
    blocks = []
    for section in sections:
        if not section.links:
            continue
        blocks.append(
            "        <section class=\"related-section\">\n"
            f"          <h2>{html_attr(section.title)}</h2>\n"
            "          <ul class=\"link-grid\">\n"
            f"              {render_link_list(section.links)}\n"
            "          </ul>\n"
            "        </section>"
        )
    return "\n".join(blocks)


def render_home_category_cards(hub_suffixes: list[str]) -> str:
    """Render home category cards from generated national hub suffixes."""

    descriptions = {
        "수학과외": "개념부터 심화까지 수학 학습의 모든 것",
        "영어과외": "독해, 문법, 어휘까지 영어 실력 완성",
        "초등과외": "기초 습관과 자신감을 키우는 초등 학습",
        "중등과외": "내신과 수행평가를 완벽하게 대비",
        "고등과외": "수능과 내신을 모두 준비하는 고등 학습",
        "초등수학과외": "연산, 도형, 문장제로 수학 자신감 키우기",
        "중등수학과외": "개념 이해와 문제 해결 능력을 키우는 수학",
        "고등수학과외": "수능 수학과 심화 학습 전문 가이드",
        "초등영어과외": "말하기, 읽기, 쓰기의 기초를 탄탄하게",
        "중등영어과외": "내신과 문법, 독해를 한번에 잡는 영어",
        "고등영어과외": "수능 영어와 내신을 동시에 대비",
        "학습전략가이드": "공부 습관, 시간 관리, 성적 향상 전략",
    }
    icon_classes = {
        "수학과외": "math",
        "영어과외": "english",
        "초등과외": "elementary",
        "중등과외": "middle",
        "고등과외": "high",
        "초등수학과외": "math",
        "중등수학과외": "math",
        "고등수학과외": "math",
        "초등영어과외": "english",
        "중등영어과외": "english",
        "고등영어과외": "english",
        "학습전략가이드": "strategy",
    }
    icon_labels = {
        "수학과외": "÷",
        "영어과외": "ABC",
        "초등과외": "초",
        "중등과외": "중",
        "고등과외": "고",
        "초등수학과외": "+",
        "중등수학과외": "∠",
        "고등수학과외": "√x",
        "초등영어과외": "ABC",
        "중등영어과외": "Book",
        "고등영어과외": "Globe",
        "학습전략가이드": "Plan",
    }
    cards = []
    for suffix in hub_suffixes:
        class_name = html_attr(icon_classes.get(suffix, "strategy"))
        label = html_attr(icon_labels.get(suffix, suffix[:1]))
        title = html_attr(suffix)
        description = html_attr(descriptions.get(suffix, f"{suffix} 학습 정보"))
        cards.append(
            f'            <a class="category-card" href="{html_attr(slug_to_relative_url(suffix))}">\n'
            f'              <span class="category-card-icon {class_name}" aria-hidden="true">{label}</span>\n'
            f"              <strong>{title}</strong>\n"
            f"              <span>{description}</span>\n"
            "              <span class=\"category-arrow\" aria-hidden=\"true\">›</span>\n"
            "            </a>"
        )
    return "\n".join(cards)


def render_home_region_cards(parent_map: dict[str, str], existing_slugs: set[str]) -> str:
    """Render city cards with district links from the configured region tree."""

    theme_by_city = {
        "대전": "region-daejeon",
        "대구": "region-daegu",
    }
    cards = []
    for city in config.HOME_CITY_ORDER:
        city_slug = f"{city}{REGION_SUFFIX}"
        district_links = []
        for child_slug in child_region_slugs(city_slug, parent_map):
            if child_slug in existing_slugs:
                district_links.append(
                    f'                  <a href="{html_attr(slug_to_relative_url(child_slug))}">{html_attr(child_slug)}</a>'
                )
        cards.append(
            f'            <article class="region-card {html_attr(theme_by_city.get(city, "region-daejeon"))}">\n'
            "              <div class=\"region-pin\" aria-hidden=\"true\">\n"
            "                <svg viewBox=\"0 0 24 24\" focusable=\"false\"><path d=\"M12 21s7-6.1 7-12a7 7 0 0 0-14 0c0 5.9 7 12 7 12z\"></path><circle cx=\"12\" cy=\"9\" r=\"2.5\"></circle></svg>\n"
            "              </div>\n"
            "              <div class=\"region-content\">\n"
            f"                <h3>{html_attr(city)}</h3>\n"
            "                <div class=\"district-grid\">\n"
            f"{chr(10).join(district_links)}\n"
            "                </div>\n"
            f'                <a class="region-more" href="{html_attr(slug_to_relative_url(city_slug))}">{html_attr(city)} 전체 지역 보기</a>\n'
            "              </div>\n"
            "            </article>"
        )
    return "\n".join(cards)


def website_json_ld() -> str:
    """Return JSON-LD for the WebSite entity."""

    payload = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": absolute_url("/#website"),
        "name": config.PROJECT_NAME,
        "url": config.BASE_URL,
        "description": config.DEFAULT_DESCRIPTION,
        "publisher": {"@id": absolute_url("/#organization")},
    }
    if config.SOCIAL_PROFILES:
        payload["sameAs"] = config.SOCIAL_PROFILES
    return json.dumps(payload, ensure_ascii=False, indent=2)


def page_json_ld(page: Page) -> str:
    """Return page-level JSON-LD while keeping WebSite data on every page."""

    page_url = absolute_url(page.url_path)
    image_url = absolute_url(root_asset_path(select_og_image_path(page)))
    graph = [
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "@id": absolute_url("/#organization"),
            "name": config.PROJECT_NAME,
            "url": config.BASE_URL,
            "logo": absolute_url(config.FAVICON_PATH),
        },
        json.loads(website_json_ld()),
        {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "@id": page_url,
            "name": page.title,
            "url": page_url,
            "description": page.description,
            "image": image_url,
            "isPartOf": {"@id": absolute_url("/#website")},
            "publisher": {"@id": absolute_url("/#organization")},
        },
    ]
    return json.dumps(graph, ensure_ascii=False, indent=2)


def page_context(page: Page, renderer: TemplateRenderer) -> dict[str, str]:
    canonical_url = absolute_url(page.url_path)
    image_path = root_asset_path(select_og_image_path(page))
    image_url = absolute_url(image_path)
    current_year = str(date.today().year)
    relative_prefix = output_relative_prefix(page.output_path)

    context = {
        "site_name": config.PROJECT_NAME,
        "language": config.LANGUAGE,
        "title": html_attr(page.title),
        "description": html_attr(page.description),
        "canonical_url": canonical_url,
        "og_title": html_attr(page.title),
        "og_description": html_attr(page.description),
        "og_url": canonical_url,
        "og_image": image_url,
        "twitter_title": html_attr(page.title),
        "twitter_description": html_attr(page.description),
        "twitter_image": image_url,
        "favicon_path": relative_asset_path(config.FAVICON_PATH, relative_prefix),
        "favicon_ico_path": relative_asset_path("assets/images/favicon.ico", relative_prefix),
        "favicon_png_path": relative_asset_path("assets/images/favicon-32x32.png", relative_prefix),
        "apple_touch_icon_path": relative_asset_path("assets/images/apple-touch-icon.png", relative_prefix),
        "stylesheet_path": relative_asset_path("assets/css/main.css", relative_prefix),
        "search_script_path": relative_asset_path("assets/js/search.js", relative_prefix),
        "home_hero_image_path": relative_asset_path("assets/images/home-hero-books-skyline-crop.png", relative_prefix),
        "asset_prefix": relative_prefix,
        "home_url": relative_prefix or "./",
        "body_class": page.body_class,
        "navigation": render_navigation(config.NAVIGATION_ITEMS, relative_prefix),
        "breadcrumbs": render_breadcrumbs(page),
        "json_ld": page_json_ld(page),
        "current_year": current_year,
        "keyword": html_attr(page.keyword),
        "body_html": page.body_html,
        "related_sections": render_link_sections(page.link_sections),
        **page.extra_context,
    }

    context["header"] = renderer.partial("header", context)
    context["footer"] = renderer.partial("footer", context)
    context["breadcrumb"] = renderer.partial("breadcrumb", context)
    return context


def render_page(page: Page, renderer: TemplateRenderer) -> None:
    context = page_context(page, renderer)
    body = renderer.render(page.template, context)
    context["content"] = body
    html_output = renderer.render("base.html", context)

    target_path = config.OUTPUT_DIR / page.output_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(html_output, encoding="utf-8", newline="\n")


def infer_hub_suffixes(rows: list[WorkbookRow]) -> list[str]:
    """Infer the 12 hub suffixes from sheet-level city keywords only.

    A naive prefix match treats values such as "대구남구과외" as a city hub
    suffix of "남구과외". Grouping by sheet and taking the shortest city
    keyword in that sheet keeps the suffix list aligned with the workbook's
    intended main hubs.
    """

    suffixes: list[str] = []
    rows_by_sheet: dict[str, list[WorkbookRow]] = {}
    for row in rows:
        rows_by_sheet.setdefault(row.sheet_name, []).append(row)

    for sheet_rows in rows_by_sheet.values():
        sheet_suffix = ""
        for city in config.HOME_CITY_ORDER:
            candidates = [
                row.keyword.removeprefix(city)
                for row in sheet_rows
                if row.keyword.startswith(city) and row.keyword.removeprefix(city).endswith(REGION_SUFFIX)
            ]
            if candidates:
                sheet_suffix = min(candidates, key=len)
                break
        if sheet_suffix and sheet_suffix not in suffixes:
            suffixes.append(sheet_suffix)
    return suffixes


def build_region_parent_map(existing_slugs: set[str]) -> dict[str, str]:
    """Return child region slug to parent region slug, using only existing pages."""

    parent_map: dict[str, str] = {}
    for city in config.CITY_NAMES:
        city_slug = f"{city}{REGION_SUFFIX}"
        if city_slug in existing_slugs:
            parent_map[city_slug] = ""

    for parent_region, child_regions in config.REGION_CHILDREN.items():
        parent_slug = f"{parent_region}{REGION_SUFFIX}"
        if parent_slug not in existing_slugs:
            continue
        for child_region in child_regions:
            child_slug = f"{child_region}{REGION_SUFFIX}"
            if child_slug in existing_slugs:
                parent_map[child_slug] = parent_slug

    return parent_map


def split_keyword(keyword: str, hub_suffixes: list[str]) -> tuple[str, str]:
    """Split a keyword into region name and hub suffix by longest suffix match."""

    for suffix in sorted(hub_suffixes, key=len, reverse=True):
        if keyword.endswith(suffix):
            return keyword[: -len(suffix)], suffix
    return keyword.removesuffix(REGION_SUFFIX), REGION_SUFFIX


def region_slug(region_name: str) -> str:
    return f"{region_name}{REGION_SUFFIX}"


def link_for_slug(slug: str, existing_slugs: set[str], prefix: str = "../") -> LinkItem | None:
    """Return a LinkItem only when the slug is backed by an Excel row."""

    if slug not in existing_slugs:
        return None
    return LinkItem(label=slug, url=prefix + slug_to_relative_url(slug))


def national_hub_suffixes(hub_suffixes: list[str]) -> list[str]:
    """Return national hub slugs derived from workbook suffixes plus configured extensions."""

    suffixes = [suffix for suffix in hub_suffixes if suffix != REGION_SUFFIX]
    for suffix in getattr(config, "EXTRA_NATIONAL_HUB_SUFFIXES", ()):
        if suffix not in suffixes:
            suffixes.append(suffix)
    return suffixes


def virtual_region_hub_slugs(national_suffixes: list[str], parent_map: dict[str, str], existing_slugs: set[str]) -> set[str]:
    """Create non-Excel region hub slugs only for configured extra national hubs."""

    virtual_slugs: set[str] = set()
    extra_suffixes = set(getattr(config, "EXTRA_NATIONAL_HUB_SUFFIXES", ()))
    region_names = [slug.removesuffix(REGION_SUFFIX) for slug in parent_map]
    for suffix in national_suffixes:
        if suffix not in extra_suffixes:
            continue
        for region_name in region_names:
            slug = f"{region_name}{suffix}"
            if slug not in existing_slugs:
                virtual_slugs.add(slug)
    return virtual_slugs


def child_region_slugs(parent_slug: str, parent_map: dict[str, str]) -> list[str]:
    children = [child for child, parent in parent_map.items() if parent == parent_slug]
    return sorted(children, key=config.REGION_ORDER.index)


def breadcrumb_for_keyword(keyword: str, hub_suffixes: list[str], parent_map: dict[str, str]) -> tuple[BreadcrumbItem, ...]:
    """Build Home > city > district > dong > current-page breadcrumbs."""

    region_name, suffix = split_keyword(keyword, hub_suffixes)
    current_region_slug = region_slug(region_name)
    chain: list[str] = []

    cursor = current_region_slug
    while cursor:
        chain.append(cursor)
        cursor = parent_map.get(cursor, "")
    chain.reverse()

    crumbs = [BreadcrumbItem("홈", "../")]
    for region in chain:
        crumbs.append(BreadcrumbItem(region, "../" + slug_to_relative_url(region)))

    if suffix != REGION_SUFFIX:
        crumbs.append(BreadcrumbItem(keyword, "../" + slug_to_relative_url(keyword)))
    return tuple(crumbs)


def related_sections_for_keyword(
    keyword: str,
    hub_suffixes: list[str],
    existing_slugs: set[str],
    parent_map: dict[str, str],
) -> tuple[LinkSection, ...]:
    """Build region and hub links according to the StudyRoute rules."""

    region_name, suffix = split_keyword(keyword, hub_suffixes)
    current_region_slug = region_slug(region_name)
    sections: list[LinkSection] = []

    if suffix == REGION_SUFFIX:
        region_children = [
            link
            for child in child_region_slugs(current_region_slug, parent_map)
            if (link := link_for_slug(child, existing_slugs)) is not None
        ]
        if region_children:
            sections.append(LinkSection("인근 지역", tuple(region_children)))

        local_hubs = [
            link
            for hub_suffix in hub_suffixes
            if hub_suffix != REGION_SUFFIX
            if (link := link_for_slug(f"{region_name}{hub_suffix}", existing_slugs)) is not None
        ]
        if local_hubs:
            sections.append(LinkSection("같은 지역의 학습 정보", tuple(local_hubs)))
    else:
        sibling_hubs = [
            link
            for hub_suffix in hub_suffixes
            if hub_suffix not in {REGION_SUFFIX, suffix}
            if (link := link_for_slug(f"{region_name}{hub_suffix}", existing_slugs)) is not None
        ]
        if sibling_hubs:
            sections.append(LinkSection("같은 지역의 학습 정보", tuple(sibling_hubs)))

        child_hubs = [
            link
            for child in child_region_slugs(current_region_slug, parent_map)
            for child_region_name in [child.removesuffix(REGION_SUFFIX)]
            if (link := link_for_slug(f"{child_region_name}{suffix}", existing_slugs)) is not None
        ]
        if child_hubs:
            sections.append(LinkSection("주변 지역의 학습 정보", tuple(child_hubs)))

    return tuple(sections)


def build_home_page(rows: list[WorkbookRow], hub_suffixes: list[str], existing_slugs: set[str]) -> Page:
    city_links = [
        link
        for city in config.HOME_CITY_ORDER
        if (link := link_for_slug(f"{city}{REGION_SUFFIX}", existing_slugs, "")) is not None
    ]

    hub_blocks = []
    for suffix in hub_suffixes:
        if suffix == REGION_SUFFIX:
            continue
        links = []
        for city in config.HOME_CITY_ORDER:
            city_hub_slug = f"{city}{suffix}"
            if link := link_for_slug(city_hub_slug, existing_slugs, ""):
                links.append(link)
        hub_blocks.append(
            "          <article class=\"hub-card\">\n"
            f"            <h2>{html_attr(suffix)}</h2>\n"
            "            <ul>\n"
            f"              {render_link_list(links)}\n"
            "            </ul>\n"
            "          </article>"
        )

    return Page(
        output_path="index.html",
        template="pages/index.html",
        title=config.DEFAULT_TITLE,
        description=config.DEFAULT_DESCRIPTION,
        breadcrumbs=(BreadcrumbItem("홈", "./"),),
        body_class="home-page",
        extra_context={
            "home_city_links": render_link_list(city_links),
            "home_hub_cards": "\n".join(hub_blocks),
            "total_pages": str(len(rows)),
        },
    )


def breadcrumb_for_national_hub(slug: str) -> tuple[BreadcrumbItem, ...]:
    return (
        BreadcrumbItem("홈", "../"),
        BreadcrumbItem(slug, "../" + slug_to_relative_url(slug)),
    )


def build_national_hub_pages(national_suffixes: list[str], existing_slugs: set[str]) -> list[Page]:
    """Build /수학과외/ style nationwide hub pages."""

    pages: list[Page] = []
    for suffix in national_suffixes:
        output_path = slug_to_output_path(suffix)
        city_links = [
            link
            for city in config.HOME_CITY_ORDER
            if (link := link_for_slug(f"{city}{suffix}", existing_slugs)) is not None
        ]
        pages.append(
            Page(
                output_path=output_path,
                template="pages/content.html",
                title=f"{suffix} | 전국 학습 허브 | {config.PROJECT_NAME}",
                description=f"{suffix} 전국 허브에서 대전과 대구 지역별 학습 정보로 이동할 수 있습니다.",
                keyword=suffix,
                body_html=(
                    f"<p>{html_attr(suffix)} 전국 허브는 대전과 대구의 지역별 학습 정보를 한곳에서 비교할 수 있도록 구성한 출발 페이지입니다. "
                    "학생의 학년, 과목 이해도, 시험 준비 상황은 지역과 학교 생활에 따라 다르게 나타날 수 있으므로 먼저 큰 지역을 선택한 뒤 세부 지역 정보를 확인하는 방식이 효율적입니다.</p>"
                    "<h2>지역을 먼저 선택해야 하는 이유</h2>"
                    "<p>같은 과목이라도 학생이 생활하는 지역, 학교 일정, 통학 시간, 수행평가 방식에 따라 필요한 학습 계획이 달라집니다. "
                    f"{html_attr(suffix)} 정보를 살펴볼 때는 현재 거주 지역에서 연결되는 구와 동 단위 정보를 함께 확인하면 더 현실적인 학습 방향을 정할 수 있습니다. "
                    "StudyRoute는 전국 허브에서 도시별 페이지로 이동한 뒤, 다시 구와 동 단위 페이지로 이어지는 구조를 제공합니다.</p>"
                    "<ul>"
                    "<li>대전과 대구 중 먼저 확인할 지역을 선택합니다.</li>"
                    "<li>선택한 지역의 구, 동 페이지에서 더 가까운 학습 정보를 확인합니다.</li>"
                    "<li>같은 지역의 수학, 영어, 학년별 정보를 함께 비교합니다.</li>"
                    "<li>학생의 시험 준비와 복습 습관에 맞는 우선순위를 정합니다.</li>"
                    "</ul>"
                    "<h2>학습 정보를 비교하는 기준</h2>"
                    "<p>지역별 정보를 볼 때는 단순히 페이지 이름만 확인하기보다 학생에게 필요한 학습 목표를 먼저 정리하는 것이 좋습니다. "
                    "개념 복습이 필요한지, 문제 풀이 속도를 높여야 하는지, 내신과 수행평가를 함께 준비해야 하는지에 따라 확인해야 할 정보가 달라집니다. "
                    f"{html_attr(suffix)} 허브는 이런 탐색을 빠르게 시작할 수 있도록 대전과 대구의 대표 지역 페이지를 연결합니다.</p>"
                    "<h3>활용 순서</h3>"
                    "<p>먼저 도시를 선택하고, 이어서 구와 동 단위 페이지를 확인한 뒤 같은 지역의 다른 학습 정보를 비교해 보세요. "
                    "이 과정을 거치면 학생의 생활권과 학습 목표에 맞는 정보를 더 빠르게 찾을 수 있고, 불필요한 탐색 시간을 줄일 수 있습니다.</p>"
                ),
                breadcrumbs=breadcrumb_for_national_hub(suffix),
                link_sections=(LinkSection("관련 지역", tuple(city_links)),),
                body_class="content-page national-hub-page",
                canonical_path=slug_to_canonical_path(suffix),
                extra_context={
                    "page_heading": f"<h1>{html_attr(suffix)}</h1>",
                    "body_image_html": render_body_image(suffix, output_relative_prefix(output_path)),
                },
            )
        )
    return pages


def build_virtual_region_hub_pages(
    virtual_slugs: set[str],
    national_suffixes: list[str],
    existing_slugs: set[str],
    parent_map: dict[str, str],
) -> list[Page]:
    """Build configured extra hub pages for every existing region level."""

    pages: list[Page] = []
    for keyword in sorted(virtual_slugs):
        output_path = slug_to_output_path(keyword)
        region_name, suffix = split_keyword(keyword, national_suffixes)
        current_region_slug = region_slug(region_name)
        sibling_links = [
            link
            for hub_suffix in national_suffixes
            if hub_suffix != suffix
            if (link := link_for_slug(f"{region_name}{hub_suffix}", existing_slugs)) is not None
        ]
        child_links = [
            link
            for child in child_region_slugs(current_region_slug, parent_map)
            for child_region_name in [child.removesuffix(REGION_SUFFIX)]
            if (link := link_for_slug(f"{child_region_name}{suffix}", existing_slugs)) is not None
        ]
        sections: list[LinkSection] = []
        if sibling_links:
            sections.append(LinkSection("같은 지역의 학습 정보", tuple(sibling_links)))
        if child_links:
            sections.append(LinkSection("주변 지역의 학습 정보", tuple(child_links)))
        pages.append(
            Page(
                output_path=output_path,
                template="pages/content.html",
                title=f"{keyword} | 학습전략가이드 | {config.PROJECT_NAME}",
                description=f"{keyword} 페이지에서 지역별 학습 전략 연결 정보를 확인할 수 있습니다.",
                keyword=keyword,
                body_html=(
                    f"<p>{html_attr(keyword)} 페이지는 지역별 학습 환경을 기준으로 학생의 공부 흐름을 점검하고, "
                    "학년과 과목에 맞는 학습 방향을 정리할 수 있도록 구성한 안내 페이지입니다. "
                    "학교 생활, 시험 일정, 과목별 난이도, 가정에서의 학습 습관을 함께 살펴보면 현재 필요한 전략을 더 분명하게 찾을 수 있습니다.</p>"
                    "<h2>학습 전략을 세울 때 확인할 점</h2>"
                    "<p>효과적인 학습 계획은 단순히 공부 시간을 늘리는 방식만으로 완성되지 않습니다. "
                    "학생이 어려움을 느끼는 과목, 반복해서 틀리는 유형, 숙제를 미루는 습관, 시험 전 긴장도처럼 실제 학습을 흔드는 요인을 함께 봐야 합니다. "
                    f"{html_attr(keyword)}에서는 이런 요소를 지역 학습 정보와 연결해 살펴볼 수 있도록 관련 페이지를 함께 제공합니다.</p>"
                    "<ul>"
                    "<li>최근 시험과 수행평가에서 반복된 실수 원인을 확인합니다.</li>"
                    "<li>평일과 주말의 공부 시간을 나누어 현실적인 복습 계획을 세웁니다.</li>"
                    "<li>수학, 영어, 학년별 학습 정보 중 현재 우선순위가 높은 항목을 먼저 비교합니다.</li>"
                    "<li>인근 지역과 같은 지역의 학습 정보를 함께 확인해 선택 범위를 넓힙니다.</li>"
                    "</ul>"
                    "<h2>학부모가 함께 점검하면 좋은 부분</h2>"
                    "<p>학부모 입장에서는 성적 결과만 보기보다 학생이 어떤 과정에서 막히는지 확인하는 것이 중요합니다. "
                    "오답을 다시 보는 시간이 충분한지, 개념 설명을 스스로 말할 수 있는지, 시험 기간이 아닐 때도 일정한 복습 루틴이 유지되는지 살펴보면 학습 계획의 빈틈을 줄일 수 있습니다. "
                    "StudyRoute의 지역별 연결 구조는 이런 판단에 필요한 주변 학습 정보를 빠르게 찾을 수 있도록 돕습니다.</p>"
                    "<h3>활용 방법</h3>"
                    f"<p>{html_attr(keyword)}를 확인한 뒤에는 같은 지역의 과목별 정보와 주변 지역 페이지를 함께 살펴보는 것이 좋습니다. "
                    "학생의 현재 수준에 맞는 과목, 학년, 지역 정보를 차례대로 비교하면 불필요한 탐색을 줄이고 더 구체적인 학습 방향을 정할 수 있습니다.</p>"
                ),
                breadcrumbs=breadcrumb_for_keyword(keyword, national_suffixes, parent_map),
                link_sections=tuple(sections),
                body_class="content-page national-hub-page",
                canonical_path=slug_to_canonical_path(keyword),
                extra_context={
                    "page_heading": f"<h1>{html_attr(keyword)}</h1>",
                    "body_image_html": render_body_image(keyword, output_relative_prefix(output_path)),
                },
            )
        )
    return pages


def build_home_page(
    rows: list[WorkbookRow],
    national_suffixes: list[str],
    existing_slugs: set[str],
    parent_map: dict[str, str],
) -> Page:
    """Build the redesigned home page from generated hub and region data."""

    return Page(
        output_path="index.html",
        template="pages/index.html",
        title=config.DEFAULT_TITLE,
        description=config.DEFAULT_DESCRIPTION,
        breadcrumbs=(BreadcrumbItem("홈", "./"),),
        body_class="home-page",
        extra_context={
            "home_category_cards": render_home_category_cards(national_suffixes),
            "home_region_cards": render_home_region_cards(parent_map, existing_slugs),
            "total_pages": str(len(rows)),
        },
    )


def build_pages() -> list[Page]:
    """Read workbook data and return all pages for the current build."""

    rows = read_workbook_rows(find_workbook())
    rows_by_keyword: dict[str, WorkbookRow] = {}
    for row in rows:
        rows_by_keyword[row.keyword] = row

    excel_slugs = set(rows_by_keyword)
    hub_suffixes = infer_hub_suffixes(rows)
    national_suffixes = national_hub_suffixes(hub_suffixes)
    parent_map = build_region_parent_map(excel_slugs)
    virtual_slugs = virtual_region_hub_slugs(national_suffixes, parent_map, excel_slugs)
    existing_slugs = excel_slugs | set(national_suffixes) | virtual_slugs

    pages = [build_home_page(list(rows_by_keyword.values()), national_suffixes, existing_slugs, parent_map)]
    pages.extend(build_national_hub_pages(national_suffixes, existing_slugs))
    pages.extend(build_virtual_region_hub_pages(virtual_slugs, national_suffixes, existing_slugs, parent_map))
    for keyword in sorted(rows_by_keyword, key=lambda slug: page_sort_key(slug, hub_suffixes)):
        row = rows_by_keyword[keyword]
        output_path = slug_to_output_path(keyword)
        body_html = extract_body_fragment(row.body_html)
        body_html = supplement_short_content(keyword, body_html)
        body_image_html = render_body_image(keyword, output_relative_prefix(output_path))
        has_source_h1 = body_has_keyword_h1(body_html, keyword)
        if has_source_h1:
            body_html = strip_leading_h1_and_body_image(body_html, keyword)
        pages.append(
            Page(
                output_path=output_path,
                template="pages/content.html",
                title=build_page_title(keyword, row.sheet_name),
                description=build_meta_description(keyword, row.sheet_name),
                keyword=keyword,
                body_html=body_html,
                breadcrumbs=breadcrumb_for_keyword(keyword, hub_suffixes, parent_map),
                link_sections=related_sections_for_keyword(keyword, national_suffixes, existing_slugs, parent_map),
                body_class="content-page",
                canonical_path=slug_to_canonical_path(keyword),
                extra_context={
                    "page_heading": f"<h1>{html_attr(keyword)}</h1>",
                    "body_image_html": body_image_html,
                },
            )
        )

    return pages


def build_page_title(keyword: str, sheet_name: str) -> str:
    """Build page title from the A-column keyword and current worksheet name."""

    return f"{keyword} | {sheet_name} | {config.PROJECT_NAME}"


def build_meta_description(keyword: str, sheet_name: str) -> str:
    """Create a unique technical SEO description without changing body HTML."""

    return (
        f"{keyword} 관련 {sheet_name} 정보를 StudyRoute에서 확인하세요. "
        "지역별 과외 학습 흐름과 연결 페이지를 안내합니다."
    )


def page_sort_key(slug: str, hub_suffixes: list[str]) -> tuple[int, int, str]:
    """Sort by region order first, then hub order, then keyword."""

    region_name, suffix = split_keyword(slug, hub_suffixes)
    base_region_slug = region_slug(region_name)
    try:
        region_index = config.REGION_ORDER.index(base_region_slug)
    except ValueError:
        region_index = len(config.REGION_ORDER)
    try:
        hub_index = hub_suffixes.index(suffix)
    except ValueError:
        hub_index = len(hub_suffixes)
    return region_index, hub_index, slug


def write_robots() -> None:
    policy = "Allow: /" if config.ROBOTS_ALLOW_ALL else "Disallow: /"
    content = "\n".join(
        [
            "User-agent: *",
            policy,
            "",
            f"Sitemap: {absolute_url('/sitemap.xml')}",
            "",
        ]
    )
    (config.OUTPUT_DIR / "robots.txt").write_text(content, encoding="utf-8", newline="\n")


def write_sitemap(pages: Iterable[Page]) -> None:
    url_nodes = []
    today = date.today().isoformat()
    for page in pages:
        loc = xml_escape(absolute_url(page.url_path))
        priority = "1.0" if page.output_path == "index.html" else "0.8"
        url_nodes.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            "    <changefreq>weekly</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(url_nodes)
        + "\n</urlset>\n"
    )
    (config.OUTPUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8", newline="\n")


def write_search_index(pages: Iterable[Page]) -> None:
    """Write the client-side search index from generated page metadata."""

    records = []
    for page in pages:
        slug = page.keyword
        if not slug and page.output_path != "index.html":
            slug = page.output_path.replace("\\", "/").removesuffix("/index.html")
        records.append(
            {
                "url": page.url_path,
                "title": page.title,
                "slug": slug,
            }
        )

    payload = {
        "generated_at": date.today().isoformat(),
        "count": len(records),
        "pages": records,
    }
    (config.OUTPUT_DIR / "search-index.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )


def build_site() -> None:
    ensure_source_directories()
    clean_output()

    renderer = TemplateRenderer(config.TEMPLATE_DIR)
    pages = build_pages()
    for page in pages:
        render_page(page, renderer)

    copy_assets()
    write_search_index(pages)
    write_robots()
    write_sitemap(pages)


def main() -> None:
    build_site()
    print(f"StudyRoute build complete: {config.OUTPUT_DIR}")


if __name__ == "__main__":
    main()
