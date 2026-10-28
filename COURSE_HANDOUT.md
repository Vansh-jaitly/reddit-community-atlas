# Course Handout — CSE3729: Computational Social Media Analysis

**Course Code**: CSE3729  
**Course Name**: Computational Social Media Analysis  
**Credits**: 3 (2-0-0)  
**Contact Hours**: 2 hours Theory & 2 hours Lab per week  
**Batch**: 2023, 7th Semester  
**Academic Year**: 2026–27  
**Semester Duration**: 27th July to 28th November 2026  

---

## Course Faculty & Coordinator

- **Course Faculty**:
  1. **Dr. Kiran Sharma** (Course Coordinator)  
     *Email*: `Kiran.sharma@bmu.edu.in`  
     *Office*: Cabin #87, 4th floor, E2 building  
  2. **Dr. Jakob Bæk Kristensen**  
     *Email*: `jakobbk@ruc.dk`  
     *Office*: Cabin #87, 4th floor, E2 building  

---

## 🎯 Aim of the Course

This course aims to equip students with the theoretical foundations and practical skills required to collect, analyze, visualize, and interpret social data using computational methods. Students will learn how to transform digital traces into meaningful insights through data analytics, network science, and visualization techniques while critically evaluating the ethical, methodological, and validity challenges associated with social data analysis.

---

## 📖 Course Overview and Context

This course introduces students to computational approaches for studying social phenomena through digital media data. It covers the fundamentals of social data analytics, including data collection, cleaning, and processing using digital tools and methods. Students will develop skills in exploratory data analysis and data visualization to identify patterns and communicate insights effectively. 

The course also introduces social network analysis, including key concepts, metrics, and algorithms for understanding network structures. Finally, it emphasizes critical perspectives on data validity, encouraging students to evaluate the reliability and ethical use of social media data in research.

**Prerequisite**: Basic statistics knowledge, Basic Python coding skills.

---

## 🎓 Course Outcomes (CO)

At the end of the course, students should be able to:

| Course Outcome (CO) | Course Outcome Statement | Mapped Component | Associated Activities / Assessment |
|---|---|---|---|
| **CO1** | Understand social media data collection methods and digital analysis techniques. | Concepts Knowledge | Planned quizzes / viva / presentations and problem solving to understand knowledge gain. |
| **CO2** | Collect, analyze, and present social media data using qualitative and quantitative approaches. | Skill Development | Hands-on data collection and preprocessing sessions, case studies discussion, formulation of work objectives, synopsis design; Assessment through Project Phase Evaluation 1 & 2. |
| **CO3** | Design research strategies, evaluate data quality, and relate findings to broader social contexts. | Research Design & Decision Making | Assessment of concepts of real-life datasets and decision making through final project evaluation. |

---

## 📚 Course Modules & Syllabus

| Module | Topics | Sessions (48 Total) | Mapped COs |
|---|---|:---:|:---:|
| **Module 1: Introduction to Social Data Analytics** | Foundations of social data analytics and computational social science; Social phenomena in digital media ecosystems; Sources and characteristics of social and digital data; Computational approaches to studying human behavior and communication; Quantifying social interactions and communication patterns; Metrics and indicators for measuring social phenomena; Transforming unstructured social data into analyzable datasets; Applications of social data analytics in research and decision-making. | 6 | CO1 |
| **Module 2: Media Data Scraping & Preprocessing** | Introduction to digital methods for social media and web data collection; Search strategy design and query formulation for digital platforms; Data delimitation, sampling techniques, and dataset selection; Web scraping using Zeeschuimer and custom Python-based scrapers; Data extraction from digital platforms and online sources; Data cleaning, preprocessing, and quality assessment; Data transformation and preparation for analysis; Exporting and organizing datasets for downstream analytical workflows. | 10 | CO2 & CO3 |
| **Module 3: Media Data Analysis & Visualization** | Exploratory Data Analysis (EDA) and descriptive statistics; Understanding data distributions, central tendency, and variability; Identifying patterns, trends, and meaningful data narratives while avoiding analytical bias; Statistical summarization of social media datasets; Principles of effective data visualization and storytelling; Creating interactive charts, dashboards, and visual reports using Python and Tableau; Advanced data visualization techniques for large scale social media data; Interpreting and communicating analytical insights through visualizations. | 10 | CO2 & CO3 |
| **Module 4: Introduction to Network Analysis** | Introduction to network analysis and types of social networks: friend, user-generated, content, affiliation, etc.; Undirected and directed networks, weighted and unweighted networks, bipartite network, adjacency and incidence matrix. | 6 | CO1 |
| **Module 5: Network Metrics & Algorithms** | Network characteristics: Degree, paths, centrality, cliques, clustering coefficients, giant components, diameter, etc.; Clustering Methods: Hierarchical and k-means with hands-on; Centrality Measures: degree, closeness, betweenness, eigenvalue; Community detection algorithms: Community Detection vs Clustering, Agglomerative Methods, and Divisive Methods. | 7 | CO1 & CO2 |
| **Module 6: Critical Perspectives & Data Validity** | Digital Data Sources, Data Quality and Validity, Social Media Data Bias, Sampling and Representativeness, Data Validation Techniques, Ethical Issues in Data Collection, Critical Data Interpretation, Limitations of Online Data, Research Reliability, Digital Research Challenges. | 9 | CO1 & CO3 |

---

## 🛠️ Course Criteria & Justification

- **Application-Oriented Learning**: **Yes** — Students apply computational social science concepts through real-world projects involving social media data collection, web scraping, preprocessing, exploratory data analysis, visualization, and social network analysis using Python, Tableau, Gephi, and digital data collection tools.
- **Demonstrable Outcome**: **Yes** — Student teams develop and demonstrate an end-to-end computational social media analytics project, including data acquisition, preprocessing, analysis, visualization, network analysis, interpretation, and presentation of insights through reports, GitHub repositories, and project demonstrations.
- **Team Feasibility**: **Yes** — Projects are designed for collaborative team execution, with responsibilities distributed across data collection, preprocessing, analysis, visualization, documentation, coding, and presentations.
- **Assessability**: **Yes** — Performance is evaluated through phase-wise project reviews, technical demonstrations, code repositories, documentation, presentations, viva voce, and final project assessment.

---

## 🔗 Learning Resources & Software

### Software & Tools:
- **Zeeschuimer**: Data extraction (`https://github.com/digitalmethodsinitiative/zeeschuimer`)
- **Tableau**: Exploratory data analysis & dashboards (`tableau.com/products/desktop-free/download`)
- **Gephi**: Network analysis & visualization (`https://gephi.org`)
- **Python Data Stack**: `duckdb`, `pandas`, `networkx`, `python-igraph`, `leidenalg`, `streamlit`, `plotly`

### Data Sources:
- Instagram, LinkedIn, Twitter (X), YouTube, Reddit, Telegram

### Textbooks:
1. Wasserman, Stanley, and Katherine Faust. 1994. *Social Network Analysis: Methods and Applications*. Cambridge University Press.
2. Tanmoy Chakraborty. 2021. *Social Network Analysis*. Wiley.
3. Rogers, R. (2015). *Digital Methods for Web Research*. In Emerging Trends in the Behavioral and Social Sciences. Wiley.
4. Joshi, P. M., & Mahalle, P. N. (2023). *Data Storytelling and Visualization with Tableau: A Hands-On Approach*. CRC Press.

### Key Research References:
- Notarmuzi, D., et al. (2022). Universality, criticality and complexity of information propagation in social media. *Nature Communications*, 13(1), 1308.
- Giglietto, F., et al. (2020). It takes a village to manipulate the media: coordinated link sharing behavior during 2018 and 2019 Italian elections. *Information, Communication & Society*, 23(6), 867-891.
- Schmidt, A. L., et al. (2017). Anatomy of news consumption on Facebook. *PNAS*, 114(12), 3035-3039.
- Kristensen, J. B., Henriksen, F. M., & Mayerhöffer, E. (2023). Did COVID-19 blur partisan boundaries? *Social Media + Society*, 9(3).

---

## 📊 Assessment Pattern & Weightage

| Evaluation Component | Weightage (%) | Evaluation Week | Mapped COs | Deliverables & Focus |
|---|:---:|:---:|:---:|---|
| **A1 — Project Phase Evaluation 1** | **20%** | 1st week of Sept | CO1, CO2, CO3 | Synopsis Finalisation (5%), Problem Statement & Objectives (10%), Data Source Identification (5%). Submissions: 1-2 page synopsis, project timeline, team responsibility matrix. |
| **A2 — Project Phase Evaluation 2** | **20%** | Mid-Term Exam Week | CO1, CO2, CO3 | Data Collection & Preprocessing (10%), Data Understanding (5%), Preliminary Analysis (5%). Submissions: Updated synopsis, revised timeline, working prototype/code demonstration, progress report (1-2 pages). |
| **Quiz** | **20%** | 3rd week of Nov | CO1, CO2, CO3 | MCQ-based quiz on PrashnaSetu from complete syllabus. |
| **A3 — End Term Evaluation** | **40%** | End Term Date Sheet | CO1, CO2, CO3 | Literature Review (5%), Work Novelty (5%), Full Analysis & Inference (15%), Application/Use Case (5%), Report Writing (10%). Submissions: Final insights, source code GitHub repo, final structured report, presentation PPT & video demo, contribution matrix. |

---

## 📌 Team Responsibility & Academic Policies

### Guidelines for Team Responsibility:
- All students must contribute across core components. Roles must rotate across phases.
- No student may limit their contribution to a single area (e.g., only report writing or only data collection).
- During viva/demo evaluations, **each student must be able to explain and modify any part of the project**.

### University Policies:
- **Plagiarism & AI Policy**: Unfair Means (UFM) policy applies to any plagiarized or uncredited work.
- **Minimum Eligibility for Grading**: Students must achieve a minimum of **40% of the total marks** across all evaluation components.
- **GitHub & Video Submission**: Final source code repository must be published on GitHub, accompanied by a project demonstration video file.

