
import random
import re
import time
from collections import Counter
from datetime import date, datetime
from io import BytesIO

import streamlit as st
from PyPDF2 import PdfReader
from azure_service import extract_text_with_azure

st.set_page_config(
    page_title="SmartStudy AI",
    page_icon="📚",
    layout="wide"
)

st.markdown("""
<style>
.block-container {
    padding-top: 1.7rem;
    max-width: 1150px;
}
.hero {
    padding: 1.5rem;
    border-radius: 16px;
    background: linear-gradient(115deg, #163a68, #3659a5);
    color: white;
    margin-bottom: 1.2rem;
}
.hero h1 {
    color: white;
    margin: 0;
}
.hero p {
    color: #e5eafa;
    margin: 0.5rem 0 0;
}
</style>
""", unsafe_allow_html=True)

# SESSION STATE

DEFAULTS = {
    "notes_text": "",
    "pdf_name": "",
    "pdf_info": {},
    "pdf_page_texts": [],
    "summary": "",
    "qa_answer": "",
    "quiz": [],
    "quiz_submitted": False,
    "quiz_user_answers": {},
    "quiz_history": [],
    "study_tasks": [],
    "study_sessions": 0,
    "timer_mode": "Study",
    "timer_remaining": 25 * 60,
    "timer_end": None,
    "timer_running": False,
    "flashcards": [],
    "flashcard_index": 0,
    "flashcard_revealed": False,
    "flashcards_reviewed": [],
    "navigation": "Home",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

STOPWORDS = set("""
the a an and or but if in on at to of for from by with
is are was were be been being it this that these those
as into than then so such can could would should will
shall do does did not no you your they their we our
he she his her its about over under more most some any
all each every how what why when where who which have
has had there here also may might many much one two
three using used use
""".split())


# TEXT FUNCTIONS

def words(text):
    return re.findall(
        r"[A-Za-z][A-Za-z'-]*",
        text.lower()
    )


def sentences(text):
    return [
        x.strip()
        for x in re.split(r'(?<=[.!?])\s+|\n+', text)
        if len(x.strip()) > 25
    ]


def summarize_text(text, count=5):
    parts = sentences(text)

    if not parts:
        return "No readable sentences were found."

    freq = Counter(
        w for w in words(text)
        if w not in STOPWORDS and len(w) > 3
    )

    ranked = sorted(
        range(len(parts)),
        key=lambda i: sum(freq[w] for w in words(parts[i])),
        reverse=True
    )

    chosen = sorted(ranked[:min(count, len(parts))])

    return "\n\n".join(parts[i] for i in chosen)


def answer_question(text, question):
    question_terms = set(words(question)) - STOPWORDS

    if not question_terms:
        return "Please enter a more specific question."

    parts = sentences(text)

    scored = [
        (len(question_terms & set(words(s))), s)
        for s in parts
    ]

    if not scored or max(score for score, _ in scored) == 0:
        return "I could not find a relevant answer in the uploaded notes."

    return max(scored, key=lambda pair: pair[0])[1]


def candidate_terms(text):
    counts = Counter(
        w for w in words(text)
        if w not in STOPWORDS and len(w) >= 5
    )

    return [w for w, _ in counts.most_common(100)]


# QUIZ GENERATOR

def generate_quiz(text, number):
    pool = candidate_terms(text)
    result = []
    used = set()

    for sentence in sentences(text):
        matches = [
            w for w in words(sentence)
            if w in pool and w not in used
        ]

        if not matches:
            continue

        answer = max(
            matches,
            key=lambda w: (len(w), -pool.index(w))
        )

        alternatives = [
            w for w in pool
            if w != answer and w not in used
        ]

        if len(alternatives) < 3:
            continue

        used.add(answer)

        options = random.sample(alternatives, 3) + [answer]
        random.shuffle(options)

        blanked = re.sub(
            r'\b' + re.escape(answer) + r'\b',
            "________",
            sentence,
            count=1,
            flags=re.I
        )

        result.append({
            "question": f"Fill in the blank: {blanked}",
            "answer": answer,
            "options": options
        })

        if len(result) >= number:
            break

    return result


# FLASHCARD GENERATOR

def generate_flashcards(text, limit=15):
    pool = candidate_terms(text)
    cards = []
    used = set()

    for sentence in sentences(text):
        matches = [
            w for w in words(sentence)
            if w in pool and w not in used
        ]

        if not matches:
            continue

        answer = max(matches, key=len)
        used.add(answer)

        question = re.sub(
            r'\b' + re.escape(answer) + r'\b',
            "________",
            sentence,
            count=1,
            flags=re.I
        )

        cards.append({
            "question": question,
            "answer": answer
        })

        if len(cards) == limit:
            break

    return cards


def reset_notes_features():
    st.session_state.summary = ""
    st.session_state.qa_answer = ""
    st.session_state.quiz = []
    st.session_state.quiz_submitted = False
    st.session_state.flashcards = []
    st.session_state.flashcard_index = 0
    st.session_state.flashcard_revealed = False
    st.session_state.flashcards_reviewed = []


# LOCAL PDF EXTRACTION

def load_pdf_locally(pdf_bytes):
    reader = PdfReader(BytesIO(pdf_bytes))

    if reader.is_encrypted:
        try:
            result = reader.decrypt("")
            if result == 0:
                raise ValueError("Password required.")
        except Exception:
            raise ValueError(
                "This PDF is password protected. "
                "Please use an unlocked PDF."
            )

    pages = [
        page.extract_text() or ""
        for page in reader.pages
    ]

    return "\n\n".join(pages), pages, len(reader.pages)


# POMODORO TIMER

def timer_duration(mode):
    return {
        "Study": 25 * 60,
        "Short Break": 5 * 60,
        "Long Break": 15 * 60
    }[mode]


def update_timer():
    if (
        st.session_state.timer_running
        and st.session_state.timer_end is not None
    ):
        remaining = max(
            0,
            int(st.session_state.timer_end - time.time())
        )

        st.session_state.timer_remaining = remaining

        if remaining == 0:
            st.session_state.timer_running = False
            st.session_state.timer_end = None

            if st.session_state.timer_mode == "Study":
                st.session_state.study_sessions += 1

            st.toast("Timer finished!")


# SIDEBAR NAVIGATION

PAGES = [
    "Home",
    "Upload Notes",
    "Summarizer",
    "Ask Your Notes",
    "Quiz Generator",
    "Analytics",
    "Study Planner",
    "Pomodoro Timer",
    "Flashcards",
    "Study Recommendations"
]

with st.sidebar:
    st.title("📚 SmartStudy AI")
    st.caption("Your personal study assistant")

    page = st.radio(
        "Navigation",
        PAGES,
        key="navigation"
    )

    st.divider()
    st.caption(
        "Azure-powered PDF reading is available in Upload Notes."
    )


# DASHBOARD DATA

history = st.session_state.quiz_history
scores = [x["percentage"] for x in history]

tasks = st.session_state.study_tasks
completed_tasks = sum(bool(t["done"]) for t in tasks)
pending_tasks = len(tasks) - completed_tasks

cards = st.session_state.flashcards
reviewed = len(st.session_state.flashcards_reviewed)


# HOME PAGE

if page == "Home":

    st.markdown("""
    <div class="hero">
        <h1>Welcome to SmartStudy AI 📚</h1>
        <p>
        Study smarter with notes, quizzes, flashcards
        and Azure-powered document reading.
        </p>
    </div>
    """, unsafe_allow_html=True)

    a, b, c, d = st.columns(4)

    a.metric(
        "Notes Uploaded",
        int(bool(st.session_state.notes_text))
    )

    b.metric("Quizzes Attempted", len(history))
    c.metric("Study Sessions", st.session_state.study_sessions)
    d.metric("Pending Tasks", pending_tasks)

    st.subheader("Your Learning Progress")

    a, b = st.columns(2)

    with a:
        st.metric(
            "Average Quiz Score",
            f"{sum(scores)/len(scores):.1f}%" if scores else "—"
        )

        st.metric(
            "Best Quiz Score",
            f"{max(scores):.1f}%" if scores else "—"
        )

    with b:
        st.write("Study Planner Progress")

        st.progress(
            completed_tasks / len(tasks) if tasks else 0
        )

        st.caption(
            f"{completed_tasks} of {len(tasks)} tasks completed"
        )

        st.write("Flashcard Review Progress")

        st.progress(
            reviewed / len(cards) if cards else 0
        )

        st.caption(
            f"{reviewed} of {len(cards)} flashcards reviewed"
        )

    st.subheader("Quick Access")

    a, b, c = st.columns(3)

    if a.button("📄 Upload Notes", use_container_width=True):
        st.session_state.navigation = "Upload Notes"
        st.rerun()

    if b.button("📝 Summarizer", use_container_width=True):
        st.session_state.navigation = "Summarizer"
        st.rerun()

    if c.button("🧠 Quiz Generator", use_container_width=True):
        st.session_state.navigation = "Quiz Generator"
        st.rerun()

    st.info(
        "Start by uploading a PDF. "
        "Choose local extraction or Azure Document Intelligence."
    )


# UPLOAD NOTES - AZURE INTEGRATED

elif page == "Upload Notes":

    st.title("📄 Upload Notes")

    st.write(
        "Upload a PDF and choose how to extract its text."
    )

    pdf = st.file_uploader(
        "Choose a PDF",
        type=["pdf"]
    )

    method = st.radio(
        "Extraction Method",
        [
            "Local (PyPDF2) — no Azure usage",
            "Azure Document Intelligence — uses free-tier quota"
        ]
    )

    if pdf is not None:

        st.caption(
            f"File: {pdf.name} · {pdf.size / 1024:.1f} KB"
        )

        if st.button(
            "Extract PDF Text",
            type="primary"
        ):

            if pdf.size > 4 * 1024 * 1024:
                st.error(
                    "For this project, please use a PDF smaller than 4 MB."
                )

            else:

                with st.spinner("Reading your PDF..."):

                    try:
                        raw = pdf.getvalue()

                        # AZURE DOCUMENT INTELLIGENCE
                        if method.startswith("Azure"):

                            extracted = extract_text_with_azure(raw)

                            if extracted.startswith((
                                "Azure Error:",
                                "Azure configuration is missing."
                            )):
                                st.error(extracted)

                            elif (
                                not extracted.strip()
                                or extracted == "No text found in document."
                            ):
                                st.warning(
                                    "Azure could not find readable text."
                                )

                            else:
                                st.session_state.notes_text = extracted

                                st.session_state.pdf_page_texts = [
                                    extracted
                                ]

                                st.session_state.pdf_info = {
                                    "method": "Azure Document Intelligence"
                                }

                                st.session_state.pdf_name = pdf.name

                                reset_notes_features()

                                st.success(
                                    "PDF text extracted using Microsoft Azure!"
                                )

                        # LOCAL PYPDF2 EXTRACTION
                        else:

                            extracted, page_texts, page_count = (
                                load_pdf_locally(raw)
                            )

                            if not extracted.strip():
                                st.warning(
                                    "No selectable text found. "
                                    "Try Azure for scanned PDFs."
                                )

                            else:
                                st.session_state.notes_text = extracted

                                st.session_state.pdf_page_texts = (
                                    page_texts
                                )

                                st.session_state.pdf_info = {
                                    "method": "Local PyPDF2",
                                    "pages": page_count
                                }

                                st.session_state.pdf_name = pdf.name

                                reset_notes_features()

                                st.success(
                                    "PDF text extracted locally!"
                                )

                    except Exception as exc:
                        st.error(
                            f"Could not process PDF: {exc}"
                        )

    if st.session_state.notes_text:

        st.subheader("Current Notes")

        st.write(
            f"**File:** {st.session_state.pdf_name}"
        )

        st.write(
            "**Method:** "
            + st.session_state.pdf_info.get(
                "method", "Unknown"
            )
        )

        st.metric(
            "Extracted Words",
            len(words(st.session_state.notes_text))
        )

        with st.expander("Preview Extracted Text"):

            st.text_area(
                "PDF Text",
                st.session_state.notes_text,
                height=300
            )


# SUMMARIZER

elif page == "Summarizer":

    st.title("📝 Summarizer")

    if not st.session_state.notes_text:
        st.info("Upload a PDF first.")

    else:

        count = st.slider(
            "Number of Summary Sentences",
            2, 15, 5
        )

        if st.button(
            "Generate Summary",
            type="primary"
        ):
            st.session_state.summary = summarize_text(
                st.session_state.notes_text,
                count
            )

        if st.session_state.summary:

            st.subheader("Summary")
            st.write(st.session_state.summary)

            st.download_button(
                "Download Summary",
                st.session_state.summary,
                "summary.txt"
            )


# ASK YOUR NOTES

elif page == "Ask Your Notes":

    st.title("❓ Ask Your Notes")

    if not st.session_state.notes_text:
        st.info("Upload a PDF first.")

    else:

        question = st.text_input(
            "Ask a question about your uploaded notes"
        )

        if st.button(
            "Find Answer",
            type="primary"
        ):

            if question.strip():
                st.session_state.qa_answer = answer_question(
                    st.session_state.notes_text,
                    question
                )

            else:
                st.warning("Enter a question first.")

        if st.session_state.qa_answer:

            st.write(
                "**Most relevant sentence from your notes:**"
            )

            st.info(st.session_state.qa_answer)

        st.caption(
            "This feature finds relevant text in your notes. "
            "It does not generate new factual answers."
        )


# QUIZ GENERATOR

elif page == "Quiz Generator":

    st.title("🧠 Quiz Generator")

    if not st.session_state.notes_text:
        st.info("Upload a PDF first.")

    else:

        count = st.slider(
            "Number of Questions",
            3, 15, 5
        )

        if st.button(
            "Generate Quiz",
            type="primary"
        ):

            st.session_state.quiz = generate_quiz(
                st.session_state.notes_text,
                count
            )

            st.session_state.quiz_submitted = False
            st.session_state.quiz_user_answers = {}

            st.session_state.quiz_id = (
                st.session_state.get("quiz_id", 0) + 1
            )

        if st.session_state.quiz:

            with st.form("quiz_form"):

                answers = {}

                for i, item in enumerate(
                    st.session_state.quiz
                ):

                    st.write(
                        f"**Question {i+1}:** {item['question']}"
                    )

                    answers[i] = st.radio(
                        "Choose an answer",
                        ["Select an answer"] + item["options"],
                        key=(
                            f"quiz_"
                            f"{st.session_state.get('quiz_id', 0)}_{i}"
                        )
                    )

                submitted = st.form_submit_button(
                    "Submit Quiz"
                )

            if submitted:

                if any(
                    a == "Select an answer"
                    for a in answers.values()
                ):
                    st.warning(
                        "Please answer every question before submitting."
                    )

                elif st.session_state.quiz_submitted:
                    st.info(
                        "This quiz has already been submitted."
                    )

                else:

                    st.session_state.quiz_user_answers = (
                        answers.copy()
                    )

                    st.session_state.quiz_submitted = True

                    correct = sum(
                        answers[i] == item["answer"]
                        for i, item in enumerate(
                            st.session_state.quiz
                        )
                    )

                    percentage = round(
                        100 * correct / len(st.session_state.quiz),
                        1
                    )

                    st.session_state.quiz_history.append({
                        "date": datetime.now().strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                        "correct": correct,
                        "total": len(st.session_state.quiz),
                        "percentage": percentage,
                        "missed": [
                            item["answer"]
                            for i, item in enumerate(
                                st.session_state.quiz
                            )
                            if answers[i] != item["answer"]
                        ]
                    })

            if st.session_state.quiz_submitted:

                latest = st.session_state.quiz_history[-1]

                st.success(
                    f"Score: {latest['correct']}/"
                    f"{latest['total']} "
                    f"({latest['percentage']}%)"
                )

                for i, item in enumerate(
                    st.session_state.quiz
                ):

                    selected = (
                        st.session_state.quiz_user_answers[i]
                    )

                    mark = (
                        "✅"
                        if selected == item["answer"]
                        else "❌"
                    )

                    st.write(
                        f"{mark} **Question {i+1}:** "
                        f"Your answer: {selected} · "
                        f"Correct answer: **{item['answer']}**"
                    )

        else:
            st.caption(
                "Generate a quiz to begin."
            )


# ANALYTICS

elif page == "Analytics":

    st.title("📊 Quiz Analytics")

    if not history:
        st.info(
            "Complete a quiz to see your performance here."
        )

    else:

        a, b, c = st.columns(3)

        a.metric("Attempts", len(history))

        b.metric(
            "Average Score",
            f"{sum(scores)/len(scores):.1f}%"
        )

        c.metric(
            "Best Score",
            f"{max(scores):.1f}%"
        )

        st.subheader("Performance Trend")

        st.line_chart({
            "Quiz Score (%)": scores
        })

        st.subheader("Quiz History")

        st.dataframe(
            [
                {
                    "Date": x["date"],
                    "Correct": x["correct"],
                    "Total": x["total"],
                    "Score (%)": x["percentage"]
                }
                for x in history
            ],
            use_container_width=True
        )

        missed = Counter(
            w
            for x in history
            for w in x["missed"]
        )

        st.subheader("Topics to Review")

        if missed:

            for term, number in missed.most_common(8):
                st.write(
                    f"• **{term}** — missed {number} time(s)"
                )

        else:
            st.success(
                "No missed answers recorded yet."
            )


# STUDY PLANNER

elif page == "Study Planner":

    st.title("📅 Study Planner")

    with st.form("add_task"):

        subject = st.text_input("Subject")
        description = st.text_input("Task Description")

        deadline = st.date_input(
            "Deadline",
            value=date.today()
        )

        add = st.form_submit_button("Add Task")

    if add:

        if subject.strip() and description.strip():

            st.session_state.study_tasks.append({
                "id": time.time_ns(),
                "subject": subject.strip(),
                "description": description.strip(),
                "deadline": deadline.isoformat(),
                "done": False
            })

            st.rerun()

        else:
            st.warning(
                "Enter both subject and task description."
            )

    st.subheader("Your Tasks")

    if not tasks:
        st.info(
            "No tasks yet. Add your first study task above."
        )

    else:

        st.progress(
            completed_tasks / len(tasks)
        )

        st.caption(
            f"{completed_tasks}/{len(tasks)} completed"
        )

        for task in list(tasks):

            a, b = st.columns([6, 1])

            with a:

                checked = st.checkbox(
                    f"{task['subject']}: "
                    f"{task['description']} "
                    f"(Due {task['deadline']})",
                    value=task["done"],
                    key=f"task_{task['id']}"
                )

                if checked != task["done"]:
                    task["done"] = checked
                    st.rerun()

            with b:

                if st.button(
                    "Delete",
                    key=f"delete_{task['id']}"
                ):

                    st.session_state.study_tasks = [
                        t for t in tasks
                        if t["id"] != task["id"]
                    ]

                    st.rerun()


# POMODORO TIMER

elif page == "Pomodoro Timer":

    st.title("⏱️ Pomodoro Timer")

    modes = [
        "Study",
        "Short Break",
        "Long Break"
    ]

    mode = st.selectbox(
        "Timer Mode",
        modes,
        index=modes.index(
            st.session_state.timer_mode
        )
    )

    if mode != st.session_state.timer_mode:

        st.session_state.timer_mode = mode

        st.session_state.timer_remaining = (
            timer_duration(mode)
        )

        st.session_state.timer_running = False
        st.session_state.timer_end = None

    @st.fragment(run_every="1s")
    def timer_display():

        update_timer()

        remaining = (
            st.session_state.timer_remaining
        )

        st.markdown(
            f"<h1 style='text-align:center;"
            f"font-size:4rem'>"
            f"{remaining//60:02d}:"
            f"{remaining%60:02d}</h1>",
            unsafe_allow_html=True
        )

        a, b, c = st.columns(3)

        if a.button(
            "▶ Start",
            use_container_width=True
        ):

            if not st.session_state.timer_running:

                st.session_state.timer_end = (
                    time.time()
                    + st.session_state.timer_remaining
                )

                st.session_state.timer_running = True

            st.rerun()

        if b.button(
            "⏸ Pause",
            use_container_width=True
        ):

            update_timer()

            st.session_state.timer_running = False
            st.session_state.timer_end = None

            st.rerun()

        if c.button(
            "↺ Reset",
            use_container_width=True
        ):

            st.session_state.timer_running = False
            st.session_state.timer_end = None

            st.session_state.timer_remaining = (
                timer_duration(
                    st.session_state.timer_mode
                )
            )

            st.rerun()

    timer_display()

    st.metric(
        "Completed Study Sessions",
        st.session_state.study_sessions
    )

    st.caption(
        "Study: 25 min · Short break: 5 min · "
        "Long break: 15 min."
    )


# FLASHCARDS

elif page == "Flashcards":

    st.title("🗂️ Flashcards")

    if not st.session_state.notes_text:
        st.info("Upload a PDF first.")

    else:

        if st.button(
            "Generate Flashcards",
            type="primary"
        ):

            st.session_state.flashcards = (
                generate_flashcards(
                    st.session_state.notes_text
                )
            )

            st.session_state.flashcard_index = 0
            st.session_state.flashcard_revealed = False
            st.session_state.flashcards_reviewed = []

        if cards:

            index = st.session_state.flashcard_index
            card = cards[index]

            st.caption(
                f"Card {index+1} of {len(cards)}"
            )

            st.progress(
                reviewed / len(cards)
            )

            with st.container(border=True):

                st.subheader(
                    card["question"]
                )

                if st.session_state.flashcard_revealed:

                    st.success(
                        f"Answer: {card['answer']}"
                    )

            if st.button("Show / Hide Answer"):

                st.session_state.flashcard_revealed = (
                    not st.session_state.flashcard_revealed
                )

                if (
                    st.session_state.flashcard_revealed
                    and index not in
                    st.session_state.flashcards_reviewed
                ):

                    st.session_state.flashcards_reviewed.append(
                        index
                    )

                st.rerun()

            a, b, c = st.columns(3)

            if a.button(
                "← Previous",
                disabled=index == 0
            ):

                st.session_state.flashcard_index -= 1
                st.session_state.flashcard_revealed = False

                st.rerun()

            if b.button(
                "Next →",
                disabled=index >= len(cards)-1
            ):

                st.session_state.flashcard_index += 1
                st.session_state.flashcard_revealed = False

                st.rerun()

            if c.button("Reset Review"):

                st.session_state.flashcards_reviewed = []
                st.session_state.flashcard_index = 0
                st.session_state.flashcard_revealed = False

                st.rerun()

            st.caption(
                f"{reviewed} of {len(cards)} reviewed"
            )

        else:
            st.caption(
                "Generate flashcards from your notes to begin."
            )


# STUDY RECOMMENDATIONS

elif page == "Study Recommendations":

    st.title("💡 Study Recommendations")

    st.write(
        "Suggestions based on your study activity:"
    )

    suggestions = []

    if not st.session_state.notes_text:

        suggestions.append(
            "Upload a PDF to start creating summaries, "
            "quizzes, and flashcards."
        )

    else:

        suggestions.append(
            "Review your uploaded notes and "
            "generate a short summary."
        )

    if not history:

        suggestions.append(
            "Try a quiz to check your understanding."
        )

    elif sum(scores)/len(scores) < 70:

        suggestions.append(
            "Review the questions you missed, "
            "then take another quiz."
        )

    else:

        suggestions.append(
            "Keep practicing with new questions "
            "to maintain your progress."
        )

    missed = Counter(
        w for h in history
        for w in h["missed"]
    )

    if missed:

        suggestions.append(
            "Focus on these missed terms: "
            + ", ".join(
                w for w, _ in missed.most_common(5)
            )
        )

    if pending_tasks:

        suggestions.append(
            f"You have {pending_tasks} "
            "unfinished study task(s)."
        )

    else:

        suggestions.append(
            "Add a study task to plan your next session."
        )

    if cards and reviewed < len(cards):

        suggestions.append(
            f"Review your remaining "
            f"{len(cards)-reviewed} flashcard(s)."
        )

    if st.session_state.study_sessions == 0:

        suggestions.append(
            "Try a 25-minute Pomodoro study session."
        )

    for item in suggestions:
        st.info(item)

    st.subheader("Suggested Daily Routine")

    st.write(
        "Read notes → Summarize → "
        "Study for 25 minutes → "
        "Practice flashcards → "
        "Take a quiz → Review mistakes."
    )
