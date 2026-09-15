"""Builds the India-focused BCA / B.Sc. stream taxonomy configs.

Emits backend/configs/stream_<key>.json for every stream defined in STREAMS
below and rewrites backend/configs/streams.json (preserving the existing
'cse'/'ece' entries, adding degree metadata).

Design (matches the existing config-driven architecture):
  - One CATALOG of canonical skills (stable `code` = canonical identity).
    The DB keeps skills per stream (`unique(stream, code)`), so the same
    canonical code appearing in many streams is intentional reuse, exactly
    like the existing cse/ece configs. No duplicate spellings: every
    synonym lives in `aliases`.
  - Per-stream skill TIERS reuse the existing `demand_weight` column
    (stream-scoped by design): core=1.2 (stream-defining=1.3),
    specialized=1.0, industry-enhancement=0.85.
  - target_roles use the existing gap-analysis contract
    (name + required [{code, weight}]).
  - Run:  python scripts/build_stream_configs.py
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIGS = Path(__file__).resolve().parent.parent / "configs"

# ---------------------------------------------------------------------------
# Canonical skill catalog: code -> (label, category, aliases, default_weight)
# Codes already used by configs/stream_cse.json keep their identity; new codes
# extend the same namespace. Categories follow the existing vocabulary
# (Programming, Fundamentals, Data, Web, AI/ML, Cloud, DevOps, Security,
#  Tools, Quality, Soft Skills) plus Mobile / Embedded / Blockchain /
#  Software Engineering / Business for the new academic streams.
# ---------------------------------------------------------------------------
CATALOG: dict[str, tuple[str, str, list[str], float]] = {
    # Programming languages
    "python": ("Python", "Programming", ["py", "python3"], 1.0),
    "java": ("Java", "Programming", ["core java", "jvm", "spring boot"], 1.0),
    "cpp": ("C++", "Programming", ["c plus plus", "cpp", "stl"], 0.9),
    "c": ("C", "Programming", ["c language"], 0.9),
    "javascript": ("JavaScript", "Programming", ["js", "es6", "ecmascript"], 1.0),
    "typescript": ("TypeScript", "Programming", ["ts"], 0.9),
    "kotlin": ("Kotlin", "Programming", ["kotlin jvm"], 0.9),
    "dart": ("Dart", "Programming", ["dart language"], 0.8),
    "r": ("R", "Programming", ["r language", "r programming", "rstudio"], 0.9),
    "solidity": ("Solidity", "Blockchain", ["solidity smart contracts"], 0.9),
    # Fundamentals
    "programming_fundamentals": ("Programming Fundamentals", "Fundamentals", ["programming basics", "coding fundamentals", "programming"], 1.0),
    "oop": ("Object-Oriented Programming", "Fundamentals", ["oop", "object oriented programming", "oops concepts"], 1.0),
    "dsa": ("Data Structures & Algorithms", "Fundamentals", ["dsa", "data structures", "algorithms", "problem solving", "complexity analysis", "competitive programming"], 1.1),
    "os": ("Operating Systems", "Fundamentals", ["os concepts", "processes and threads", "memory management"], 1.0),
    "networks": ("Computer Networks", "Fundamentals", ["networking", "computer network", "osi model"], 1.0),
    "computer_fundamentals": ("Computer Fundamentals", "Fundamentals", ["computer basics", "computing fundamentals"], 0.8),
    "computer_architecture": ("Computer Architecture", "Fundamentals", ["microprocessors", "memory hierarchy", "instruction set"], 0.9),
    "theory_of_computation": ("Theory of Computation", "Fundamentals", ["automata theory", "toc", "formal languages"], 0.7),
    "computer_graphics": ("Computer Graphics", "Fundamentals", ["graphics programming", "opengl", "rendering"], 0.7),
    "mathematics": ("Mathematics for Computing", "Fundamentals", ["engineering mathematics", "maths", "math"], 0.9),
    "discrete_math": ("Discrete Mathematics", "Fundamentals", ["discrete structures", "graph theory", "combinatorics"], 0.8),
    "linear_algebra": ("Linear Algebra", "Fundamentals", ["matrices", "vectors", "eigenvalues"], 0.8),
    "calculus": ("Calculus Fundamentals", "Fundamentals", ["differentiation", "integration"], 0.7),
    "physics": ("Physics Fundamentals", "Fundamentals", ["physics", "mechanics", "optics"], 0.7),
    "tcp_ip": ("TCP/IP", "Fundamentals", ["tcp ip stack", "ip addressing", "dns", "dhcp"], 0.9),
    "system_design": ("System Design", "Fundamentals", ["scalability", "basic system design", "architecture", "distributed systems"], 1.0),
    # Databases / Data
    "dbms": ("DBMS", "Data", ["database management", "database management system", "rdbms"], 1.1),
    "sql": ("SQL", "Data", ["structured query language", "queries", "joins"], 1.1),
    "mysql": ("MySQL", "Data", ["my sql", "mariadb"], 0.9),
    "postgresql": ("PostgreSQL", "Data", ["postgres", "psql"], 0.9),
    "sqlserver": ("SQL Server", "Data", ["microsoft sql server", "mssql", "t-sql"], 0.8),
    "mongodb": ("MongoDB", "Data", ["nosql", "document database", "mongo"], 0.8),
    "sqlite": ("SQLite", "Data", ["sqlite3", "embedded database"], 0.8),
    "database_design": ("Database Design", "Data", ["schema design", "relational schema"], 1.0),
    "er_modeling": ("ER Modeling", "Data", ["entity relationship diagram", "er diagram", "erd"], 0.8),
    "normalization": ("Database Normalization", "Data", ["normal forms", "1nf 2nf 3nf", "denormalization"], 0.8),
    "query_optimization": ("Indexing & Query Optimization", "Data", ["indexing", "query tuning", "execution plans"], 0.8),
    "transactions": ("Transactions & ACID", "Data", ["acid properties", "concurrency control"], 0.8),
    "stored_procedures": ("Stored Procedures", "Data", ["triggers", "pl/sql", "procedures"], 0.7),
    "backup_recovery": ("Backup & Recovery", "Data", ["database backup", "restore", "dumps"], 0.7),
    "db_security": ("Database Security", "Security", ["database hardening", "database access control"], 0.7),
    "pandas": ("Pandas", "Data", ["dataframes", "data wrangling"], 1.0),
    "numpy": ("NumPy", "Data", ["numerical python", "ndarray"], 0.9),
    "matplotlib": ("Matplotlib", "Data", ["pyplot", "seaborn", "plotting"], 0.8),
    "data_cleaning": ("Data Cleaning", "Data", ["data munging", "missing values", "outlier treatment"], 0.9),
    "eda": ("Exploratory Data Analysis", "Data", ["eda", "data analysis", "data exploration"], 0.9),
    "data_viz": ("Data Visualization", "Data", ["charts", "visual analytics", "graphs"], 0.9),
    "excel": ("Excel", "Data", ["microsoft excel", "spreadsheets", "pivot tables", "vlookup"], 0.9),
    "powerbi": ("Power BI", "Data", ["power bi desktop", "dax"], 0.9),
    "tableau": ("Tableau", "Data", ["tableau desktop", "tableau public"], 0.9),
    "sql_analytics": ("Analytics & BI", "Data", ["bi", "dashboards", "reporting", "kpi tracking"], 0.9),
    "statistics": ("Statistics", "Data", ["statistical methods", "descriptive statistics", "inferential statistics"], 1.0),
    "probability": ("Probability", "Data", ["probability theory", "distributions"], 0.9),
    "regression": ("Regression Modeling", "Data", ["linear regression", "logistic regression"], 0.8),
    "hypothesis_testing": ("Hypothesis Testing", "Data", ["t-test", "p-values", "confidence intervals"], 0.8),
    "statistical_modeling": ("Statistical Modeling", "Data", ["glm", "anova", "statistical models"], 0.8),
    "experimental_design": ("Experimental Design", "Data", ["a/b testing", "design of experiments"], 0.7),
    "data_mining": ("Data Mining", "Data", ["pattern mining", "association rules"], 0.8),
    "big_data": ("Big Data Fundamentals", "Data", ["hadoop", "hdfs", "hive"], 0.8),
    "spark": ("Apache Spark", "Data", ["pyspark", "spark sql"], 0.8),
    "time_series": ("Time Series Analysis", "Data", ["forecasting", "arima"], 0.8),
    "cloud_data": ("Cloud Data Platforms", "Cloud", ["data warehouse", "bigquery", "redshift", "snowflake"], 0.8),
    "data_engineering": ("Data Engineering", "Data", ["etl", "data pipelines", "airflow"], 0.9),
    "dashboarding": ("Dashboarding & Reporting", "Data", ["mis reporting", "dashboards"], 0.8),
    "business_analytics": ("Business Analytics", "Business", ["analytics for business", "business insights"], 0.8),
    "jupyter": ("Jupyter", "Tools", ["jupyter notebook", "jupyterlab", "colab"], 0.7),
    "json": ("JSON", "Tools", ["json parsing", "serialization"], 0.7),
    # AI / ML
    "ml_basics": ("Machine Learning", "AI/ML", ["ml", "machine learning fundamentals", "supervised learning", "model training", "regression classifiers"], 1.1),
    "sklearn": ("Scikit-learn", "AI/ML", ["scikit learn"], 0.9),
    "deep_learning": ("Deep Learning", "AI/ML", ["neural networks", "cnn", "rnn", "transformers"], 1.0),
    "tensorflow": ("TensorFlow", "AI/ML", ["tf", "keras"], 0.9),
    "pytorch": ("PyTorch", "AI/ML", ["torch"], 0.9),
    "computer_vision": ("Computer Vision", "AI/ML", ["cv", "opencv", "image processing"], 0.9),
    "nlp": ("NLP", "AI/ML", ["natural language processing", "text mining", "language models"], 0.9),
    "model_evaluation": ("Model Evaluation", "AI/ML", ["cross validation", "precision recall", "roc auc"], 0.8),
    "data_preprocessing": ("Data Preprocessing", "Data", ["feature scaling", "encoding", "standardization"], 0.8),
    "feature_engineering": ("Feature Engineering", "AI/ML", ["feature selection", "feature extraction"], 0.8),
    "model_optimization": ("Model Optimization", "AI/ML", ["quantization", "pruning", "hyperparameter tuning"], 0.8),
    "mlops": ("MLOps Fundamentals", "AI/ML", ["model deployment", "ml pipelines"], 0.8),
    # Web
    "html": ("HTML", "Web", ["html5", "web markup"], 0.9),
    "css": ("CSS", "Web", ["css3", "stylesheets", "flexbox", "grid"], 0.9),
    "bootstrap": ("Bootstrap", "Web", ["bootstrap 5"], 0.8),
    "tailwind": ("Tailwind CSS", "Web", ["tailwindcss"], 0.8),
    "responsive_design": ("Responsive Web Design", "Web", ["responsive design", "mobile-first", "media queries"], 0.9),
    "angular": ("Angular", "Web", ["angular 2+", "ng modules"], 0.9),
    "react": ("React", "Web", ["reactjs", "react.js", "jsx", "frontend framework"], 1.0),
    "vue": ("Vue.js", "Web", ["vuejs", "vue 3"], 0.8),
    "express": ("Express.js", "Web", ["expressjs", "node express"], 0.9),
    "nodejs": ("Node.js", "Web", ["node", "node js", "npm"], 0.9),
    "rest_api": ("REST APIs", "Web", ["restful", "rest api", "api endpoints", "http services"], 1.1),
    "django": ("Django", "Web", ["django rest framework", "drf"], 0.9),
    "web_security": ("Web Security", "Security", ["web app security", "xss", "csrf", "sql injection"], 0.9),
    "ui_design": ("UI Design", "Mobile", ["user interface design", "wireframing", "material design"], 0.8),
    # Mobile
    "mobile_dev": ("Mobile Development", "Mobile", ["mobile apps", "app development"], 0.9),
    "android": ("Android Development", "Mobile", ["android sdk", "android apps"], 1.0),
    "android_studio": ("Android Studio", "Mobile", ["avd", "gradle"], 0.8),
    "flutter": ("Flutter", "Mobile", ["flutter sdk", "widgets"], 1.0),
    "react_native": ("React Native", "Mobile", ["rn", "expo"], 0.9),
    "firebase": ("Firebase", "Mobile", ["firestore", "fcm", "firebase auth"], 0.8),
    # Cloud
    "cloud_fundamentals": ("Cloud Computing", "Cloud", ["cloud computing fundamentals", "cloud basics", "cloud concepts"], 1.0),
    "aws": ("AWS", "Cloud", ["amazon web services", "ec2", "s3", "lambda"], 1.1),
    "azure": ("Microsoft Azure", "Cloud", ["azure portal", "az-900"], 1.0),
    "gcp": ("Google Cloud", "Cloud", ["gcp", "google cloud platform"], 0.9),
    "virtualization": ("Virtualization", "Cloud", ["virtual machines", "hypervisor", "vmware"], 0.8),
    "storage": ("Cloud Storage", "Cloud", ["object storage", "block storage", "buckets"], 0.8),
    "cloud_databases": ("Cloud Databases", "Cloud", ["managed databases", "dbaas", "rds"], 0.8),
    "iam": ("IAM", "Cloud", ["identity and access management", "access roles", "policies"], 0.9),
    "cloud_security": ("Cloud Security", "Security", ["cloud compliance", "cloud hardening"], 0.9),
    "cloud_deployment": ("Cloud Deployment", "Cloud", ["cloud hosting", "paas", "deploying to cloud"], 0.8),
    "cloud_iot": ("Cloud IoT", "Embedded", ["iot platforms", "aws iot", "azure iot hub"], 0.8),
    "infra_fundamentals": ("Infrastructure Fundamentals", "Cloud", ["servers", "datacenters", "infrastructure basics"], 0.7),
    # DevOps
    "git": ("Git & Version Control", "DevOps", ["git scm", "github", "version control", "pull requests", "merge conflicts"], 0.9),
    "docker": ("Docker", "DevOps", ["containers", "containerization", "dockerfiles"], 1.0),
    "ci_cd": ("CI/CD", "DevOps", ["continuous integration", "continuous deployment", "pipelines"], 1.0),
    "jenkins": ("Jenkins", "DevOps", ["jenkins pipeline"], 0.8),
    "github_actions": ("GitHub Actions", "DevOps", ["gh actions", "workflow files"], 0.8),
    "kubernetes": ("Kubernetes Fundamentals", "DevOps", ["k8s", "pods", "container orchestration"], 0.9),
    "monitoring": ("Monitoring & Logging", "DevOps", ["observability", "prometheus", "grafana", "logs"], 0.8),
    "linux": ("Linux", "Tools", ["unix", "ubuntu", "command line", "cli"], 0.9),
    "shell_scripting": ("Shell Scripting", "Tools", ["bash scripting", "bash"], 0.8),
    # Security
    "cybersecurity": ("Cybersecurity Fundamentals", "Security", ["cybersecurity basics", "infosec", "information security"], 0.9),
    "network_security": ("Network Security", "Security", ["firewalls", "ids ips", "vpn"], 1.0),
    "cryptography": ("Cryptography", "Security", ["encryption", "ciphers", "hashing", "pki"], 0.9),
    "auth": ("Authentication & Authorization", "Security", ["authentication", "authorization", "oauth", "jwt", "sso"], 0.9),
    "owasp": ("OWASP", "Security", ["owasp top 10", "owasp zap"], 0.8),
    "vuln_assessment": ("Vulnerability Assessment", "Security", ["vulnerability scanning", "nessus", "cvss"], 0.9),
    "pentest": ("Penetration Testing", "Security", ["pen testing", "pentesting", "kali linux"], 0.9),
    "ethical_hacking": ("Ethical Hacking", "Security", ["white hat hacking", "ceh"], 0.8),
    "siem": ("SIEM", "Security", ["splunk", "qradar", "security log analysis"], 0.8),
    "soc": ("SOC Fundamentals & Monitoring", "Security", ["security operations center", "security monitoring", "soc analyst"], 0.9),
    "digital_forensics": ("Digital Forensics", "Security", ["forensic analysis", "chain of custody"], 0.7),
    "incident_response": ("Incident Response", "Security", ["ir playbooks", "incident handling"], 0.7),
    # IoT / Embedded
    "iot": ("Internet of Things", "Embedded", ["iot systems", "connected devices"], 1.0),
    "embedded": ("Embedded Programming", "Embedded", ["embedded systems", "firmware", "embedded c"], 1.0),
    "microcontrollers": ("Microcontrollers", "Embedded", ["mcu", "8051", "arm cortex"], 0.9),
    "sensors": ("Sensors", "Embedded", ["sensor interfacing"], 0.8),
    "actuators": ("Actuators", "Embedded", ["motors", "relays", "servo"], 0.7),
    "esp32": ("ESP32", "Embedded", ["esp8266", "esp-idf"], 0.8),
    "arduino": ("Arduino", "Embedded", ["arduino uno", "arduino ide"], 0.8),
    "mqtt": ("MQTT", "Embedded", ["mqtt protocol", "iot messaging"], 0.8),
    "edge_computing": ("Edge Computing", "Embedded", ["edge devices", "fog computing"], 0.8),
    "data_collection": ("Data Collection & Telemetry", "Embedded", ["telemetry", "sensor data logging"], 0.7),
    "basic_electronics": ("Basic Electronics", "Embedded", ["electronics fundamentals", "circuits"], 0.7),
    # Blockchain
    "blockchain": ("Blockchain Fundamentals", "Blockchain", ["distributed ledger", "distributed ledgers"], 1.0),
    "ethereum": ("Ethereum", "Blockchain", ["eth", "evm"], 0.9),
    "smart_contracts": ("Smart Contracts", "Blockchain", ["dapps", "erc20"], 0.9),
    "web3": ("Web3 & Wallets", "Blockchain", ["web3.js", "ethers.js", "metamask", "wallets"], 0.8),
    "consensus": ("Consensus Mechanisms", "Blockchain", ["proof of work", "proof of stake"], 0.8),
    "blockchain_security": ("Blockchain Security", "Blockchain", ["smart contract audits"], 0.8),
    # Software Engineering
    "software_engineering": ("Software Engineering", "Software Engineering", ["swe principles"], 1.0),
    "sdlc": ("SDLC", "Software Engineering", ["software development life cycle", "waterfall model"], 0.9),
    "agile": ("Agile", "Software Engineering", ["agile methodology"], 0.8),
    "scrum": ("Scrum", "Software Engineering", ["sprints", "kanban", "scrum ceremonies"], 0.8),
    "requirements": ("Requirements Gathering & Analysis", "Software Engineering", ["requirements engineering", "srs"], 0.8),
    "documentation": ("Technical Documentation", "Software Engineering", ["technical writing"], 0.7),
    # IT / Support
    "it_support": ("IT Support", "Tools", ["helpdesk", "desktop support"], 0.9),
    "troubleshooting": ("Troubleshooting", "Tools", ["problem diagnosis", "technical troubleshooting"], 0.9),
    "sysadmin": ("System Administration", "Tools", ["server administration", "patching", "user management"], 0.9),
    "it_infra": ("IT Infrastructure", "Tools", ["infrastructure management"], 0.8),
    # Business / IS
    "systems_analysis": ("Systems Analysis", "Business", ["system analysis", "system study"], 0.9),
    "bpa": ("Business Process Analysis", "Business", ["process mapping", "bpm"], 0.8),
    "erp": ("ERP Fundamentals", "Business", ["erp systems", "sap", "tally"], 0.8),
    "project_management": ("Project Management", "Business", ["project planning", "gantt"], 0.7),
    "it_management": ("IT Management", "Business", ["it governance", "it service management"], 0.7),
    # Quality
    "debugging": ("Debugging", "Quality", ["debugging skills", "root cause analysis"], 0.8),
    "testing": ("Software Testing", "Quality", ["unit testing", "integration testing", "qa", "test cases"], 0.9),
    # Soft skills
    "communication": ("Professional Communication", "Soft Skills", ["presentation", "business communication"], 0.7),
    "teamwork": ("Teamwork & Collaboration", "Soft Skills", ["collaboration", "team player"], 0.7),
    "critical_thinking": ("Critical & Analytical Thinking", "Soft Skills", ["critical thinking", "analytical thinking", "problem solving"], 0.7),
    "time_management": ("Time Management", "Soft Skills", ["prioritization"], 0.7),
}

# ---------------------------------------------------------------------------
# Learning resources for the most load-bearing canonical skills.
# Existing cse entries are reused verbatim; new entries are real, mostly-free
# Indian-relevant (NPTEL) or official resources.
# ---------------------------------------------------------------------------
RESOURCES: dict[str, list[dict]] = {
    "python": [
        {"title": "Python for Everybody (Coursera)", "provider": "Coursera", "url": "https://www.coursera.org/specializations/python", "duration_hours": 40},
        {"title": "Official Python Tutorial", "provider": "python.org", "url": "https://docs.python.org/3/tutorial/", "duration_hours": 10},
    ],
    "sql": [
        {"title": "SQL Tutorial (SQLBolt)", "provider": "SQLBolt", "url": "https://sqlbolt.com/", "duration_hours": 6},
        {"title": "DBMS (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105175", "duration_hours": 30},
    ],
    "dbms": [
        {"title": "Database Management System (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105175", "duration_hours": 30},
    ],
    "dsa": [
        {"title": "Programming, Data Structures and Algorithms (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106106145", "duration_hours": 40},
    ],
    "java": [{"title": "Java Programming (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105191", "duration_hours": 40}],
    "cpp": [{"title": "C++ Course (learncpp.com)", "provider": "LearnCpp", "url": "https://www.learncpp.com/", "duration_hours": 30}],
    "c": [{"title": "C Programming (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106104128", "duration_hours": 30}],
    "oop": [{"title": "Object Oriented Analysis and Design (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105155", "duration_hours": 30}],
    "os": [{"title": "Operating Systems (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106106144", "duration_hours": 35}],
    "networks": [{"title": "Computer Networks (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105183", "duration_hours": 35}],
    "computer_architecture": [{"title": "Computer Architecture (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106103148", "duration_hours": 35}],
    "html": [{"title": "Responsive Web Design Certification", "provider": "freeCodeCamp", "url": "https://www.freecodecamp.org/learn/2022/responsive-web-design/", "duration_hours": 30}],
    "css": [{"title": "Learn CSS (web.dev)", "provider": "Google", "url": "https://web.dev/learn/css/", "duration_hours": 12}],
    "javascript": [{"title": "The Modern JavaScript Tutorial", "provider": "javascript.info", "url": "https://javascript.info/", "duration_hours": 30}],
    "typescript": [{"title": "TS Handbook", "provider": "typescriptlang.org", "url": "https://www.typescriptlang.org/docs/handbook/", "duration_hours": 10}],
    "react": [{"title": "React Official Learn Course", "provider": "react.dev", "url": "https://react.dev/learn", "duration_hours": 20}],
    "angular": [{"title": "Angular Getting Started", "provider": "Angular", "url": "https://angular.dev/tutorials", "duration_hours": 15}],
    "nodejs": [{"title": "Node.js & Express (MDN)", "provider": "MDN", "url": "https://developer.mozilla.org/en-US/docs/Learn/Server-side/Express_Nodejs", "duration_hours": 12}],
    "rest_api": [{"title": "REST API design guide (MDN)", "provider": "MDN", "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP", "duration_hours": 8}],
    "tailwind": [{"title": "Tailwind CSS Documentation", "provider": "Tailwind Labs", "url": "https://tailwindcss.com/docs", "duration_hours": 8}],
    "bootstrap": [{"title": "Bootstrap Documentation", "provider": "Bootstrap", "url": "https://getbootstrap.com/docs/", "duration_hours": 8}],
    "django": [{"title": "Django Official Tutorial", "provider": "Django", "url": "https://docs.djangoproject.com/en/stable/intro/tutorial01/", "duration_hours": 10}],
    "git": [{"title": "Pro Git book", "provider": "git-scm", "url": "https://git-scm.com/book/en/v2", "duration_hours": 8}],
    "docker": [{"title": "Docker Get Started", "provider": "Docker", "url": "https://docs.docker.com/get-started/", "duration_hours": 8}],
    "kubernetes": [{"title": "Kubernetes Basics", "provider": "kubernetes.io", "url": "https://kubernetes.io/docs/tutorials/kubernetes-basics/", "duration_hours": 10}],
    "jenkins": [{"title": "Jenkins Pipeline Tutorial", "provider": "Jenkins", "url": "https://www.jenkins.io/doc/pipeline/tour/", "duration_hours": 6}],
    "linux": [{"title": "The Missing Semester (MIT)", "provider": "MIT", "url": "https://missing.csail.mit.edu/", "duration_hours": 10}],
    "aws": [{"title": "AWS Cloud Practitioner Essentials", "provider": "AWS Skill Builder", "url": "https://skillbuilder.aws/", "duration_hours": 20}],
    "azure": [{"title": "Azure Fundamentals (AZ-900)", "provider": "Microsoft Learn", "url": "https://learn.microsoft.com/en-us/training/paths/azure-fundamentals/", "duration_hours": 16}],
    "gcp": [{"title": "Cloud Digital Leader learning path", "provider": "Google Cloud Skills Boost", "url": "https://www.cloudskillsboost.google/paths/9", "duration_hours": 12}],
    "cloud_fundamentals": [{"title": "Cloud Computing (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105167", "duration_hours": 30}],
    "pandas": [{"title": "Kaggle Pandas Micro-course", "provider": "Kaggle", "url": "https://www.kaggle.com/learn/pandas", "duration_hours": 4}],
    "numpy": [{"title": "NumPy Quickstart", "provider": "numpy.org", "url": "https://numpy.org/doc/stable/user/quickstart.html", "duration_hours": 5}],
    "excel": [{"title": "Excel Skills for Business (Coursera)", "provider": "Coursera", "url": "https://www.coursera.org/specializations/excel", "duration_hours": 40}],
    "powerbi": [{"title": "Get started with Power BI", "provider": "Microsoft Learn", "url": "https://learn.microsoft.com/en-us/training/powerplatform/power-bi", "duration_hours": 10}],
    "tableau": [{"title": "Tableau eLearning fundamentals", "provider": "Tableau", "url": "https://www.tableau.com/learn/training", "duration_hours": 12}],
    "sql_analytics": [{"title": "Google Data Analytics Certificate", "provider": "Coursera", "url": "https://www.coursera.org/professional-certificates/google-data-analytics", "duration_hours": 60}],
    "statistics": [{"title": "Statistics (Khan Academy)", "provider": "Khan Academy", "url": "https://www.khanacademy.org/math/statistics-probability", "duration_hours": 25}],
    "ml_basics": [{"title": "Machine Learning Specialization", "provider": "Coursera", "url": "https://www.coursera.org/specializations/machine-learning-introduction", "duration_hours": 60}],
    "deep_learning": [{"title": "Practical Deep Learning for Coders", "provider": "fast.ai", "url": "https://course.fast.ai/", "duration_hours": 40}],
    "tensorflow": [{"title": "TensorFlow Developer Certificate program", "provider": "TensorFlow", "url": "https://www.tensorflow.org/certificate", "duration_hours": 40}],
    "pytorch": [{"title": "PyTorch Tutorials", "provider": "PyTorch", "url": "https://pytorch.org/tutorials/", "duration_hours": 25}],
    "computer_vision": [{"title": "OpenCV Python Course", "provider": "OpenCV", "url": "https://docs.opencv.org/master/d6/d00/tutorial_py_root.html", "duration_hours": 20}],
    "nlp": [{"title": "Hugging Face NLP Course", "provider": "Hugging Face", "url": "https://huggingface.co/learn/nlp-course", "duration_hours": 25}],
    "r": [{"title": "R for Data Science (free book)", "provider": "r4ds.had.co.nz", "url": "https://r4ds.had.co.nz/", "duration_hours": 30}],
    "cybersecurity": [{"title": "Foundations of Cybersecurity (Google)", "provider": "Coursera", "url": "https://www.coursera.org/learn/foundations-of-cybersecurity", "duration_hours": 15}],
    "network_security": [{"title": "Network Security (Cisco Networking Academy)", "provider": "Cisco NetAcad", "url": "https://www.netacad.com/courses/network-security", "duration_hours": 30}],
    "pentest": [{"title": "Penetration Testing Basics", "provider": "TryHackMe", "url": "https://tryhackme.com/", "duration_hours": 20}],
    "siem": [{"title": "SOC Analyst learning path", "provider": "LetsDefend", "url": "https://letsdefend.io/", "duration_hours": 20}],
    "iot": [{"title": "Introduction to Internet of Things (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105166", "duration_hours": 30}],
    "android": [{"title": "Android Basics with Compose", "provider": "Google", "url": "https://developer.android.com/courses/android-basics-compose/course", "duration_hours": 60}],
    "flutter": [{"title": "Flutter codelabs (Google)", "provider": "Google", "url": "https://codelabs.developers.google.com/?product=flutter", "duration_hours": 20}],
    "kotlin": [{"title": "Kotlin Official Docs", "provider": "JetBrains", "url": "https://kotlinlang.org/docs/home.html", "duration_hours": 15}],
    "blockchain": [{"title": "Blockchain (NPTEL)", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/106105197", "duration_hours": 30}],
    "solidity": [{"title": "Solidity Documentation", "provider": "soliditylang.org", "url": "https://docs.soliditylang.org/en/stable/", "duration_hours": 15}],
    "ethereum": [{"title": "Ethereum Developer Portal", "provider": "ethereum.org", "url": "https://ethereum.org/en/developers/", "duration_hours": 15}],
    "mysql": [{"title": "MySQL Tutorial", "provider": "mysqltutorial.org", "url": "https://www.mysqltutorial.org/", "duration_hours": 12}],
    "mongodb": [{"title": "MongoDB University M001", "provider": "MongoDB", "url": "https://learn.mongodb.com/", "duration_hours": 7}],
    "postgresql": [{"title": "PostgreSQL Tutorial", "provider": "postgresqltutorial.com", "url": "https://www.postgresqltutorial.com/", "duration_hours": 12}],
    "testing": [{"title": "pytest documentation & course", "provider": "pytest", "url": "https://docs.pytest.org/en/stable/", "duration_hours": 6}],
    "mobile_dev": [{"title": "Flutter codelabs (Google)", "provider": "Google", "url": "https://codelabs.developers.google.com/?product=flutter", "duration_hours": 20}],
    "system_design": [{"title": "System Design Primer (GitHub)", "provider": "GitHub", "url": "https://github.com/donnemartin/system-design-primer", "duration_hours": 25}],
    "communication": [{"title": "Business English Communication (Coursera)", "provider": "Coursera", "url": "https://www.coursera.org/specializations/business-english-communication", "duration_hours": 20}],
    "erp": [{"title": "ERP Fundamentals", "provider": "NPTEL", "url": "https://nptel.ac.in/courses/110105128", "duration_hours": 20}],
}

# ---------------------------------------------------------------------------
# Stream definitions. skills: list of code or (code, tier) where tier is
# "core*" (1.3) | "core" (1.2) | "spec" (1.0) | "enh" (0.85).
# ---------------------------------------------------------------------------
W = {"core*": 1.3, "core": 1.2, "spec": 1.0, "enh": 0.85}

STREAMS: list[dict] = [
    # ================= BCA =================
    {
        "key": "bca_gen", "name": "BCA — General / Computer Applications", "degree": "BCA",
        "aliases": ["Bachelor of Computer Applications", "BCA General"],
        "skills": ["c", "cpp", "java", "python", "programming_fundamentals", "oop", ("dsa", "core"),
                   "dbms", "sql", "os", "networks", "software_engineering", "html", "css", "javascript",
                   "git", "computer_fundamentals", "debugging", ("rest_api", "enh"),
                   ("critical_thinking", "enh"), ("communication", "enh")],
        "roles": [
            ("Software Developer", [("dsa", 1.2), ("oop", 1.2), ("java", 1.0), ("python", 1.0), ("sql", 1.0), ("git", 0.8)]),
            ("Software Engineer Intern", [("programming_fundamentals", 1.3), ("dsa", 1.2), ("sql", 1.0), ("git", 0.8), ("debugging", 0.8)]),
            ("Application Developer", [("oop", 1.2), ("java", 1.1), ("dbms", 1.0), ("javascript", 1.0), ("rest_api", 0.8)]),
            ("Web Developer", [("html", 1.2), ("css", 1.2), ("javascript", 1.2), ("sql", 0.9), ("git", 0.8)]),
            ("Backend Developer", [("python", 1.2), ("sql", 1.2), ("dsa", 1.0), ("rest_api", 1.0), ("git", 0.8)]),
            ("QA Engineer", [("testing", 1.3), ("debugging", 1.0), ("sql", 0.9), ("programming_fundamentals", 1.0)]),
            ("Software Testing Intern", [("testing", 1.3), ("debugging", 0.9), ("sql", 0.8), ("communication", 0.7)]),
            ("IT Support Engineer", [("computer_fundamentals", 1.2), ("networks", 1.0), ("os", 1.0), ("troubleshooting", 1.2)]),
            ("Technical Support Engineer", [("troubleshooting", 1.3), ("networks", 0.9), ("os", 0.9), ("communication", 0.9)]),
            ("Junior Database Developer", [("sql", 1.3), ("dbms", 1.2), ("database_design", 1.0), ("python", 0.8)]),
        ],
    },
    {
        "key": "bca_web", "name": "BCA — Web Development", "degree": "BCA",
        "aliases": ["BCA Web Development"],
        "skills": [("html", "core*"), ("css", "core*"), ("javascript", "core*"), "responsive_design",
                   "bootstrap", "tailwind", "react", "angular", "vue", "nodejs", "express", "rest_api",
                   "json", "auth", "git", "sql", "mysql", "postgresql", "mongodb", "web_security",
                   ("communication", "enh")],
        "roles": [
            ("Frontend Developer", [("javascript", 1.3), ("react", 1.2), ("html", 1.2), ("css", 1.2), ("responsive_design", 1.0)]),
            ("Backend Developer", [("nodejs", 1.2), ("express", 1.1), ("rest_api", 1.2), ("sql", 1.1), ("mongodb", 0.9)]),
            ("Full Stack Developer", [("react", 1.2), ("nodejs", 1.1), ("rest_api", 1.1), ("sql", 1.0), ("git", 0.9)]),
            ("Web Developer", [("html", 1.2), ("css", 1.2), ("javascript", 1.2), ("responsive_design", 1.0), ("git", 0.8)]),
            ("UI Developer", [("html", 1.3), ("css", 1.3), ("javascript", 1.1), ("bootstrap", 0.9), ("tailwind", 0.9)]),
            ("Web Application Developer", [("javascript", 1.2), ("rest_api", 1.1), ("sql", 1.0), ("react", 1.0), ("web_security", 0.8)]),
            ("Frontend Intern", [("html", 1.3), ("css", 1.2), ("javascript", 1.2), ("react", 1.0)]),
            ("Full Stack Intern", [("javascript", 1.2), ("nodejs", 1.0), ("react", 1.0), ("sql", 0.9), ("git", 0.8)]),
        ],
    },
    {
        "key": "bca_swdev", "name": "BCA — Software Development", "degree": "BCA",
        "aliases": ["BCA Software Development"],
        "skills": ["cpp", "java", "python", "oop", "dsa", "software_engineering", "sdlc", "git",
                   "debugging", "testing", ("sql", "core"), "database_design", "rest_api", "agile",
                   "scrum", "system_design", ("communication", "enh")],
        "roles": [
            ("Software Developer", [("dsa", 1.2), ("oop", 1.2), ("python", 1.0), ("java", 1.0), ("git", 1.0)]),
            ("Software Engineer", [("dsa", 1.2), ("system_design", 1.1), ("sdlc", 1.0), ("testing", 0.9), ("sql", 1.0)]),
            ("Java Developer", [("java", 1.3), ("oop", 1.2), ("sql", 1.0), ("rest_api", 1.0), ("git", 0.9)]),
            ("Python Developer", [("python", 1.3), ("rest_api", 1.1), ("sql", 1.0), ("django", 0.9)]),
            ("Application Developer", [("oop", 1.2), ("java", 1.0), ("database_design", 1.0), ("rest_api", 1.0)]),
            ("Backend Developer", [("python", 1.1), ("sql", 1.2), ("rest_api", 1.2), ("system_design", 1.0)]),
            ("QA Engineer", [("testing", 1.3), ("debugging", 1.0), ("sdlc", 0.9), ("sql", 0.8)]),
            ("Software Engineering Intern", [("programming_fundamentals", 1.2), ("dsa", 1.2), ("git", 1.0), ("agile", 0.8)]),
        ],
    },
    {
        "key": "bca_ds", "name": "BCA — Data Science / Data Analytics", "degree": "BCA",
        "aliases": ["BCA Data Science", "BCA Data Analytics"],
        "skills": [("python", "core*"), ("sql", "core*"), ("statistics", "core"), ("probability", "spec"),
                   "numpy", "pandas", "matplotlib", "data_cleaning", "eda", "data_viz", "excel",
                   "powerbi", "tableau", "sklearn", "ml_basics", "jupyter", "git",
                   ("communication", "enh")],
        "roles": [
            ("Data Analyst", [("sql", 1.3), ("excel", 1.1), ("powerbi", 1.1), ("pandas", 1.0), ("data_viz", 1.0)]),
            ("Data Analyst Intern", [("python", 1.1), ("sql", 1.3), ("eda", 1.0), ("excel", 1.0)]),
            ("Junior Data Scientist", [("python", 1.2), ("ml_basics", 1.2), ("pandas", 1.1), ("statistics", 1.0)]),
            ("BI Analyst", [("powerbi", 1.3), ("sql", 1.2), ("tableau", 1.0), ("dashboarding", 0.9)]),
            ("Data Science Intern", [("python", 1.2), ("pandas", 1.1), ("ml_basics", 1.1), ("statistics", 1.0)]),
            ("Reporting Analyst", [("excel", 1.3), ("sql", 1.1), ("dashboarding", 1.0), ("communication", 0.8)]),
            ("Business Analyst", [("sql", 1.1), ("excel", 1.1), ("bpa", 0.9), ("communication", 1.0)]),
        ],
    },
    {
        "key": "bca_aiml", "name": "BCA — Artificial Intelligence / Machine Learning", "degree": "BCA",
        "aliases": ["BCA AI", "BCA Machine Learning", "BCA AI/ML"],
        "skills": [("python", "core*"), ("mathematics", "core"), "statistics", "probability", "linear_algebra",
                   "numpy", "pandas", "ml_basics", "sklearn", "deep_learning", "tensorflow", "pytorch",
                   "computer_vision", "nlp", "model_evaluation", "data_preprocessing", "feature_engineering",
                   "git", "jupyter"],
        "roles": [
            ("AI/ML Intern", [("python", 1.2), ("ml_basics", 1.3), ("deep_learning", 1.0), ("pandas", 1.0)]),
            ("Machine Learning Intern", [("ml_basics", 1.3), ("sklearn", 1.1), ("python", 1.2), ("statistics", 1.0)]),
            ("AI Engineer Intern", [("python", 1.3), ("deep_learning", 1.2), ("tensorflow", 1.0), ("pytorch", 1.0)]),
            ("ML Engineer Intern", [("ml_basics", 1.3), ("feature_engineering", 1.0), ("model_evaluation", 1.0), ("python", 1.2)]),
            ("Computer Vision Intern", [("computer_vision", 1.3), ("deep_learning", 1.1), ("python", 1.1)]),
            ("NLP Intern", [("nlp", 1.3), ("python", 1.1), ("deep_learning", 1.0)]),
            ("Data Science Intern", [("python", 1.2), ("pandas", 1.1), ("ml_basics", 1.1)]),
        ],
    },
    {
        "key": "bca_cyber", "name": "BCA — Cybersecurity", "degree": "BCA",
        "aliases": ["BCA Cyber Security", "BCA Security"],
        "skills": [("networks", "core"), ("tcp_ip", "core"), "linux", ("cybersecurity", "core*"),
                   "network_security", "web_security", "cryptography", "auth", "owasp",
                   "vuln_assessment", "pentest", "ethical_hacking", "siem", "soc", "digital_forensics",
                   ("python", "enh"), ("communication", "enh")],
        "roles": [
            ("Cybersecurity Intern", [("cybersecurity", 1.3), ("networks", 1.1), ("linux", 1.0), ("web_security", 1.0)]),
            ("SOC Analyst Intern", [("soc", 1.3), ("siem", 1.2), ("network_security", 1.0), ("tcp_ip", 1.0)]),
            ("Security Analyst", [("network_security", 1.2), ("vuln_assessment", 1.1), ("siem", 1.0), ("linux", 0.9)]),
            ("Security Testing Intern", [("web_security", 1.3), ("owasp", 1.2), ("vuln_assessment", 1.0), ("pentest", 0.9)]),
            ("Junior Cybersecurity Analyst", [("cybersecurity", 1.3), ("network_security", 1.0), ("cryptography", 0.9), ("tcp_ip", 1.0)]),
            ("Information Security Intern", [("cybersecurity", 1.2), ("auth", 1.0), ("cryptography", 0.9), ("owasp", 0.9)]),
        ],
    },
    {
        "key": "bca_cloud", "name": "BCA — Cloud Computing", "degree": "BCA",
        "aliases": ["BCA Cloud"],
        "skills": [("cloud_fundamentals", "core*"), ("aws", "core"), ("azure", "core"), "gcp", "linux",
                   "networks", "virtualization", "storage", "cloud_databases", "iam", "cloud_security",
                   "docker", "rest_api", "git", ("ci_cd", "enh"), ("python", "enh")],
        "roles": [
            ("Cloud Intern", [("cloud_fundamentals", 1.3), ("linux", 1.0), ("virtualization", 0.9), ("aws", 1.0)]),
            ("Cloud Support Intern", [("cloud_fundamentals", 1.3), ("troubleshooting", 1.1), ("linux", 1.0), ("iam", 0.9)]),
            ("Cloud Engineer Intern", [("aws", 1.2), ("cloud_fundamentals", 1.2), ("docker", 1.0), ("ci_cd", 0.9)]),
            ("Junior Cloud Engineer", [("aws", 1.2), ("azure", 1.0), ("cloud_security", 0.9), ("docker", 1.0)]),
            ("Cloud Operations Intern", [("monitoring", 1.1), ("linux", 1.1), ("cloud_fundamentals", 1.2), ("storage", 0.9)]),
        ],
    },
    {
        "key": "bca_devops", "name": "BCA — DevOps", "degree": "BCA",
        "aliases": ["BCA DevOps"],
        "skills": [("linux", "core"), ("git", "core"), ("docker", "core*"), ("ci_cd", "core"),
                   "jenkins", "github_actions", "kubernetes", "shell_scripting", "python",
                   "cloud_fundamentals", "aws", "azure", "gcp", "infra_fundamentals", "monitoring",
                   ("communication", "enh")],
        "roles": [
            ("DevOps Intern", [("docker", 1.3), ("ci_cd", 1.2), ("linux", 1.2), ("git", 1.1)]),
            ("DevOps Engineer Intern", [("ci_cd", 1.3), ("jenkins", 1.0), ("kubernetes", 1.0), ("docker", 1.2)]),
            ("Cloud/DevOps Intern", [("cloud_fundamentals", 1.2), ("docker", 1.2), ("ci_cd", 1.1), ("aws", 1.0)]),
            ("Junior DevOps Engineer", [("kubernetes", 1.2), ("docker", 1.2), ("monitoring", 1.0), ("shell_scripting", 1.0)]),
            ("Site Reliability Intern", [("monitoring", 1.3), ("linux", 1.1), ("python", 1.0), ("docker", 1.0)]),
        ],
    },
    {
        "key": "bca_db", "name": "BCA — Database / Database Applications", "degree": "BCA",
        "aliases": ["BCA Database"],
        "skills": [("dbms", "core*"), ("sql", "core*"), "mysql", "postgresql", "sqlserver",
                   "database_design", "er_modeling", "normalization", "query_optimization",
                   "transactions", "stored_procedures", "backup_recovery", "db_security",
                   ("python", "enh"), ("excel", "enh")],
        "roles": [
            ("SQL Developer", [("sql", 1.3), ("mysql", 1.0), ("stored_procedures", 1.0), ("query_optimization", 1.0)]),
            ("Database Developer", [("sql", 1.3), ("database_design", 1.2), ("postgresql", 1.0), ("python", 0.9)]),
            ("Database Intern", [("dbms", 1.3), ("sql", 1.3), ("er_modeling", 0.9), ("normalization", 0.9)]),
            ("Junior DBA", [("backup_recovery", 1.2), ("query_optimization", 1.1), ("sqlserver", 1.0), ("db_security", 1.0)]),
            ("Database Support Engineer", [("troubleshooting", 1.1), ("sql", 1.2), ("backup_recovery", 1.0), ("mysql", 0.9)]),
            ("Data Analyst", [("sql", 1.3), ("excel", 1.0), ("eda", 0.9), ("powerbi", 0.8)]),
        ],
    },
    {
        "key": "bca_mobile", "name": "BCA — Mobile Application Development", "degree": "BCA",
        "aliases": ["BCA Mobile App Development"],
        "skills": ["java", "kotlin", ("android", "core*"), "android_studio", ("flutter", "core"), "dart",
                   "react_native", "ui_design", "rest_api", "json", "sqlite", "firebase", "auth", "git",
                   ("javascript", "enh")],
        "roles": [
            ("Android Developer Intern", [("android", 1.3), ("kotlin", 1.2), ("android_studio", 1.0), ("rest_api", 0.9)]),
            ("Mobile App Developer", [("flutter", 1.2), ("android", 1.1), ("rest_api", 1.0), ("ui_design", 0.9)]),
            ("Flutter Developer Intern", [("flutter", 1.3), ("dart", 1.2), ("firebase", 1.0), ("rest_api", 0.9)]),
            ("Mobile Application Intern", [("mobile_dev", 1.2), ("kotlin", 1.0), ("react_native", 0.9), ("git", 0.8)]),
        ],
    },
    {
        "key": "bca_it", "name": "BCA — Information Technology", "degree": "BCA",
        "aliases": ["BCA IT"],
        "skills": [("programming_fundamentals", "core"), "python", "java", "dbms", "sql", "networks",
                   "os", "linux", ("html", "enh"), ("css", "enh"), ("javascript", "enh"),
                   "cloud_fundamentals", "sysadmin", "it_support", "troubleshooting", "cybersecurity",
                   "git"],
        "roles": [
            ("IT Support Engineer", [("it_support", 1.3), ("troubleshooting", 1.3), ("networks", 1.0), ("os", 1.0)]),
            ("System Administrator Intern", [("sysadmin", 1.3), ("linux", 1.2), ("networks", 1.0), ("os", 1.0)]),
            ("IT Analyst", [("troubleshooting", 1.1), ("sql", 1.0), ("excel", 1.0), ("communication", 0.9)]),
            ("Technical Support Engineer", [("troubleshooting", 1.3), ("it_support", 1.2), ("communication", 1.0)]),
            ("Application Support Engineer", [("troubleshooting", 1.2), ("sql", 1.1), ("linux", 0.9), ("monitoring", 0.8)]),
            ("Network Support Intern", [("networks", 1.3), ("tcp_ip", 1.1), ("troubleshooting", 1.0), ("linux", 0.9)]),
        ],
    },
    {
        "key": "bca_isys", "name": "BCA — Information Systems / Business Systems", "degree": "BCA",
        "aliases": ["BCA Information Systems"],
        "skills": [("systems_analysis", "core"), "dbms", "sql", "bpa", "requirements",
                   "software_engineering", "eda", "erp", "documentation", "project_management",
                   "excel", "communication", ("critical_thinking", "enh"), ("teamwork", "enh")],
        "roles": [
            ("Business Analyst Intern", [("bpa", 1.2), ("sql", 1.0), ("excel", 1.1), ("communication", 1.1)]),
            ("Systems Analyst", [("systems_analysis", 1.3), ("requirements", 1.2), ("sql", 1.0), ("documentation", 0.9)]),
            ("IT Analyst", [("systems_analysis", 1.1), ("sql", 1.0), ("project_management", 0.9), ("excel", 1.0)]),
            ("ERP Support Intern", [("erp", 1.3), ("sql", 1.0), ("troubleshooting", 0.9), ("communication", 0.9)]),
            ("Application Support Analyst", [("troubleshooting", 1.1), ("sql", 1.1), ("documentation", 0.9)]),
        ],
    },
    {
        "key": "bca_iot", "name": "BCA — Internet of Things (IoT)", "degree": "BCA",
        "aliases": ["BCA IoT"],
        "skills": [("iot", "core*"), "python", "c", "cpp", ("embedded", "core"), "microcontrollers",
                   "sensors", "actuators", "esp32", "arduino", "mqtt", "rest_api", "networks",
                   "cloud_iot", "edge_computing", "data_collection", "basic_electronics"],
        "roles": [
            ("IoT Intern", [("iot", 1.3), ("arduino", 1.0), ("sensors", 1.0), ("python", 1.0)]),
            ("IoT Developer Intern", [("iot", 1.3), ("embedded", 1.1), ("mqtt", 1.0), ("python", 1.0)]),
            ("Embedded Systems Intern", [("embedded", 1.3), ("microcontrollers", 1.1), ("c", 1.1), ("esp32", 0.9)]),
            ("IoT Solutions Intern", [("iot", 1.2), ("cloud_iot", 1.0), ("mqtt", 0.9), ("networks", 0.9)]),
            ("Edge Computing Intern", [("edge_computing", 1.3), ("python", 1.0), ("microcontrollers", 1.0), ("cloud_iot", 0.9)]),
        ],
    },
    {
        "key": "bca_blockchain", "name": "BCA — Blockchain", "degree": "BCA",
        "aliases": ["BCA Blockchain Technology"],
        "skills": [("blockchain", "core*"), "cryptography", "ethereum", "solidity", "smart_contracts",
                   "web3", "consensus", "nodejs", "javascript", "web_security", ("networks", "enh"),
                   ("python", "enh")],
        "roles": [
            ("Blockchain Intern", [("blockchain", 1.3), ("cryptography", 1.0), ("ethereum", 0.9)]),
            ("Blockchain Developer Intern", [("solidity", 1.3), ("smart_contracts", 1.2), ("ethereum", 1.1), ("javascript", 0.9)]),
            ("Smart Contract Developer Intern", [("solidity", 1.3), ("smart_contracts", 1.3), ("blockchain_security", 1.0)]),
            ("Web3 Developer Intern", [("web3", 1.3), ("javascript", 1.1), ("react", 0.9), ("ethereum", 1.0)]),
        ],
    },
    # ================= B.Sc. =================
    {
        "key": "bsc_cs", "name": "B.Sc Computer Science", "degree": "B.Sc",
        "aliases": ["B.Sc (Hons.) Computer Science", "BSc CS", "Bachelor of Science Computer Science"],
        "skills": [("python", "core"), "cpp", "java", "programming_fundamentals", "oop", ("dsa", "core*"),
                   "mathematics", "discrete_math", "probability", "dbms", "sql", "os", "networks",
                   "software_engineering", "computer_architecture", "theory_of_computation",
                   "computer_graphics", "git", ("ml_basics", "enh"), ("deep_learning", "enh"),
                   ("data_mining", "enh"), ("cybersecurity", "enh"), ("html", "enh"), ("cloud_fundamentals", "enh")],
        "roles": [
            ("Software Developer", [("dsa", 1.2), ("oop", 1.2), ("python", 1.0), ("cpp", 0.9), ("sql", 1.0)]),
            ("Software Engineer Intern", [("programming_fundamentals", 1.2), ("dsa", 1.3), ("git", 0.9), ("sql", 0.9)]),
            ("Backend Developer", [("python", 1.2), ("sql", 1.2), ("dsa", 1.1), ("rest_api", 1.0), ("os", 0.8)]),
            ("Data Analyst", [("sql", 1.2), ("python", 1.1), ("probability", 0.9), ("excel", 0.9)]),
            ("AI/ML Intern", [("ml_basics", 1.3), ("python", 1.2), ("statistics", 1.0), ("deep_learning", 0.9)]),
            ("Web Developer", [("html", 1.1), ("css", 1.1), ("javascript", 1.2), ("sql", 0.8)]),
            ("QA Engineer", [("testing", 1.3), ("debugging", 1.0), ("sdlc", 0.8)]),
            ("Cybersecurity Intern", [("cybersecurity", 1.3), ("networks", 1.0), ("linux", 0.9)]),
            ("Database Developer", [("sql", 1.3), ("dbms", 1.2), ("database_design", 1.0)]),
        ],
    },
    {
        "key": "bsc_it", "name": "B.Sc Information Technology", "degree": "B.Sc",
        "aliases": ["B.Sc IT", "BSc Information Technology"],
        "skills": [("programming_fundamentals", "core"), "python", "java", "cpp", "dbms", "sql",
                   ("html", "core"), ("css", "core"), ("javascript", "core"), "networks", "os", "linux",
                   "cloud_fundamentals", "sysadmin", "cybersecurity", "git", "troubleshooting",
                   "it_infra"],
        "roles": [
            ("IT Analyst", [("troubleshooting", 1.2), ("sql", 1.0), ("excel", 1.0), ("it_infra", 0.9)]),
            ("IT Support Engineer", [("it_support", 1.3), ("troubleshooting", 1.2), ("networks", 1.0)]),
            ("Software Developer", [("programming_fundamentals", 1.2), ("python", 1.0), ("sql", 1.0), ("git", 0.9)]),
            ("Web Developer", [("html", 1.2), ("css", 1.1), ("javascript", 1.2), ("sql", 0.9)]),
            ("Cloud Support Intern", [("cloud_fundamentals", 1.3), ("linux", 1.1), ("troubleshooting", 1.0)]),
            ("Network Support Engineer", [("networks", 1.3), ("tcp_ip", 1.1), ("linux", 1.0)]),
            ("System Administrator Intern", [("sysadmin", 1.3), ("linux", 1.2), ("os", 1.0)]),
        ],
    },
    {
        "key": "bsc_ds", "name": "B.Sc Data Science", "degree": "B.Sc",
        "aliases": ["BSc Data Science"],
        "skills": [("python", "core*"), ("sql", "core*"), ("statistics", "core"), "probability",
                   "numpy", "pandas", "data_cleaning", "eda", "data_viz", "matplotlib", "powerbi",
                   "tableau", "ml_basics", "sklearn", "jupyter", "excel", "r", "data_mining",
                   ("big_data", "enh"), ("spark", "enh"), ("deep_learning", "enh"), ("nlp", "enh"),
                   ("time_series", "enh"), ("cloud_data", "enh"), ("data_engineering", "enh")],
        "roles": [
            ("Data Analyst", [("sql", 1.3), ("python", 1.1), ("eda", 1.0), ("powerbi", 1.0)]),
            ("Data Scientist Intern", [("python", 1.2), ("ml_basics", 1.3), ("statistics", 1.1), ("pandas", 1.1)]),
            ("Data Science Intern", [("python", 1.2), ("pandas", 1.1), ("ml_basics", 1.1), ("sql", 1.0)]),
            ("Data Engineer Intern", [("data_engineering", 1.3), ("sql", 1.2), ("python", 1.1), ("spark", 0.9)]),
            ("BI Analyst", [("powerbi", 1.3), ("sql", 1.2), ("tableau", 1.0), ("dashboarding", 1.0)]),
            ("ML Intern", [("ml_basics", 1.3), ("sklearn", 1.1), ("python", 1.2)]),
            ("Business Intelligence Intern", [("sql", 1.1), ("powerbi", 1.1), ("excel", 1.0), ("communication", 0.9)]),
        ],
    },
    {
        "key": "bsc_ai", "name": "B.Sc Artificial Intelligence", "degree": "B.Sc",
        "aliases": ["BSc AI", "B.Sc in Artificial Intelligence"],
        "skills": [("python", "core*"), ("mathematics", "core"), ("statistics", "core"), "probability",
                   "linear_algebra", "calculus", "ml_basics", "deep_learning", "tensorflow", "pytorch",
                   "sklearn", "computer_vision", "nlp", "model_evaluation", "data_preprocessing",
                   "feature_engineering", ("jupyter", "enh"), ("git", "enh")],
        "roles": [
            ("AI Engineer Intern", [("python", 1.3), ("deep_learning", 1.2), ("tensorflow", 1.0), ("pytorch", 1.0)]),
            ("ML Engineer Intern", [("ml_basics", 1.3), ("model_evaluation", 1.1), ("feature_engineering", 1.0)]),
            ("AI/ML Intern", [("ml_basics", 1.3), ("python", 1.2), ("statistics", 1.0)]),
            ("Computer Vision Intern", [("computer_vision", 1.3), ("deep_learning", 1.1), ("python", 1.0)]),
            ("NLP Intern", [("nlp", 1.3), ("python", 1.1), ("deep_learning", 1.0)]),
            ("Data Science Intern", [("python", 1.2), ("pandas", 1.0), ("ml_basics", 1.1)]),
        ],
    },
    {
        "key": "bsc_aiml", "name": "B.Sc Artificial Intelligence & Machine Learning", "degree": "B.Sc",
        "aliases": ["B.Sc AI & ML", "BSc AIML"],
        "skills": [("python", "core*"), "statistics", "probability", "linear_algebra", ("ml_basics", "core"),
                   ("deep_learning", "core"), "tensorflow", "pytorch", "sklearn", "computer_vision",
                   "nlp", "model_evaluation", "model_optimization", "feature_engineering", "mlops", "git",
                   ("jupyter", "enh")],
        "roles": [
            ("Machine Learning Engineer Intern", [("ml_basics", 1.3), ("model_optimization", 1.0), ("python", 1.3), ("mlops", 0.9)]),
            ("AI Engineer Intern", [("deep_learning", 1.2), ("pytorch", 1.1), ("python", 1.3)]),
            ("ML Research Intern", [("model_evaluation", 1.2), ("deep_learning", 1.1), ("statistics", 1.0)]),
            ("Computer Vision Intern", [("computer_vision", 1.3), ("pytorch", 1.0), ("python", 1.1)]),
            ("NLP Intern", [("nlp", 1.3), ("deep_learning", 1.0), ("python", 1.1)]),
            ("AI/ML Intern", [("ml_basics", 1.3), ("python", 1.2), ("sklearn", 1.0)]),
        ],
    },
    {
        "key": "bsc_cyber", "name": "B.Sc Cybersecurity / Information Security", "degree": "B.Sc",
        "aliases": ["B.Sc Cyber Security", "B.Sc Information Security"],
        "skills": [("networks", "core"), "linux", ("cybersecurity", "core*"), "cryptography",
                   "network_security", "web_security", "auth", ("ethical_hacking", "core"),
                   "vuln_assessment", "pentest", "owasp", "siem", "soc", "digital_forensics",
                   "incident_response", ("python", "enh")],
        "roles": [
            ("Cybersecurity Intern", [("cybersecurity", 1.3), ("network_security", 1.0), ("linux", 1.0)]),
            ("SOC Analyst Intern", [("soc", 1.3), ("siem", 1.2), ("network_security", 1.0)]),
            ("Security Analyst", [("vuln_assessment", 1.2), ("siem", 1.0), ("network_security", 1.2)]),
            ("Information Security Intern", [("cybersecurity", 1.2), ("cryptography", 1.0), ("auth", 1.0)]),
            ("Vulnerability Assessment Intern", [("vuln_assessment", 1.3), ("owasp", 1.1), ("pentest", 1.0)]),
            ("Security Operations Intern", [("soc", 1.2), ("incident_response", 1.1), ("siem", 1.0)]),
        ],
    },
    {
        "key": "bsc_cloud", "name": "B.Sc Cloud Computing", "degree": "B.Sc",
        "aliases": ["BSc Cloud Computing"],
        "skills": [("cloud_fundamentals", "core*"), ("aws", "core"), ("azure", "core"), "gcp", "linux",
                   "virtualization", "networks", "storage", "cloud_databases", "iam", "cloud_security",
                   "docker", "kubernetes", "git", "cloud_deployment", "monitoring"],
        "roles": [
            ("Cloud Intern", [("cloud_fundamentals", 1.3), ("virtualization", 1.0), ("linux", 1.0)]),
            ("Cloud Support Engineer", [("troubleshooting", 1.2), ("cloud_fundamentals", 1.2), ("linux", 1.1)]),
            ("Cloud Engineer Intern", [("aws", 1.2), ("docker", 1.1), ("kubernetes", 1.0), ("ci_cd", 0.9)]),
            ("Cloud Operations Intern", [("monitoring", 1.2), ("linux", 1.1), ("storage", 0.9)]),
        ],
    },
    {
        "key": "bsc_swdev", "name": "B.Sc Software Development / Software Technology", "degree": "B.Sc",
        "aliases": ["B.Sc Software Technology"],
        "skills": ["cpp", "java", "python", "oop", "dsa", "software_engineering", "sdlc", "git",
                   "testing", "debugging", "dbms", "sql", "rest_api", "html", "css", "javascript",
                   "agile", "scrum"],
        "roles": [
            ("Software Developer", [("dsa", 1.2), ("oop", 1.2), ("java", 1.0), ("sql", 1.0)]),
            ("Software Engineer Intern", [("programming_fundamentals", 1.2), ("dsa", 1.2), ("git", 1.0)]),
            ("Application Developer", [("oop", 1.2), ("python", 1.0), ("rest_api", 1.0), ("sql", 1.0)]),
            ("Backend Developer", [("python", 1.1), ("sql", 1.2), ("rest_api", 1.2), ("dsa", 1.0)]),
            ("QA Engineer", [("testing", 1.3), ("debugging", 1.0), ("sdlc", 0.9)]),
            ("Full Stack Developer", [("javascript", 1.2), ("html", 1.0), ("css", 1.0), ("rest_api", 1.1), ("sql", 1.0)]),
        ],
    },
    {
        "key": "bsc_web", "name": "B.Sc Web Development / Web Technologies", "degree": "B.Sc",
        "aliases": ["B.Sc Web Technologies"],
        "skills": [("html", "core*"), ("css", "core*"), ("javascript", "core*"), "typescript",
                   "react", "angular", "vue", "nodejs", "express", "rest_api", "json",
                   "responsive_design", "ui_design", "web_security", "git", "sql", "mongodb"],
        "roles": [
            ("Frontend Developer", [("javascript", 1.3), ("react", 1.2), ("html", 1.1), ("css", 1.1)]),
            ("Backend Developer", [("nodejs", 1.2), ("express", 1.1), ("rest_api", 1.2), ("sql", 1.1)]),
            ("Full Stack Developer", [("react", 1.2), ("nodejs", 1.1), ("rest_api", 1.1), ("mongodb", 0.9)]),
            ("Web Developer", [("html", 1.2), ("css", 1.2), ("javascript", 1.2), ("responsive_design", 1.0)]),
            ("UI Developer", [("html", 1.3), ("css", 1.3), ("ui_design", 1.0), ("javascript", 1.0)]),
        ],
    },
    {
        "key": "bsc_mobile", "name": "B.Sc Mobile Application Development", "degree": "B.Sc",
        "aliases": ["B.Sc Mobile App Development"],
        "skills": [("android", "core*"), "java", "kotlin", "android_studio", "flutter", "dart",
                   "react_native", "firebase", "rest_api", "sqlite", "ui_design", "auth", "git",
                   ("javascript", "enh")],
        "roles": [
            ("Android Developer Intern", [("android", 1.3), ("kotlin", 1.2), ("android_studio", 1.0)]),
            ("Mobile App Developer", [("flutter", 1.1), ("android", 1.1), ("rest_api", 1.0)]),
            ("Flutter Developer", [("flutter", 1.3), ("dart", 1.2), ("firebase", 1.0)]),
            ("Mobile Application Intern", [("mobile_dev", 1.2), ("react_native", 0.9), ("git", 0.8)]),
        ],
    },
    {
        "key": "bsc_da", "name": "B.Sc Data Analytics", "degree": "B.Sc",
        "aliases": ["BSc Data Analytics"],
        "skills": [("statistics", "core"), ("python", "core"), ("sql", "core"), "excel", "pandas",
                   "numpy", "data_cleaning", "eda", "data_viz", "powerbi", "tableau", "dashboarding",
                   "business_analytics", "documentation", ("communication", "enh")],
        "roles": [
            ("Data Analyst", [("sql", 1.3), ("excel", 1.1), ("powerbi", 1.1), ("pandas", 1.0)]),
            ("Business Analyst", [("bpa", 1.0), ("excel", 1.1), ("sql", 1.0), ("communication", 1.1)]),
            ("BI Analyst", [("powerbi", 1.3), ("tableau", 1.1), ("sql", 1.1), ("dashboarding", 1.0)]),
            ("Reporting Analyst", [("dashboarding", 1.3), ("excel", 1.2), ("sql", 1.0)]),
            ("Data Analyst Intern", [("python", 1.0), ("sql", 1.3), ("eda", 1.0)]),
        ],
    },
    {
        "key": "bsc_stats", "name": "B.Sc Statistics / Statistics with Computing", "degree": "B.Sc",
        "aliases": ["B.Sc Statistics with Computing"],
        "skills": [("statistics", "core*"), ("probability", "core"), ("statistical_modeling", "core"),
                   "regression", "hypothesis_testing", "r", "python", "sql", "excel", "data_viz",
                   "experimental_design", "eda", ("ml_basics", "enh")],
        "roles": [
            ("Statistical Analyst", [("statistical_modeling", 1.3), ("regression", 1.2), ("r", 1.1)]),
            ("Data Analyst", [("sql", 1.2), ("excel", 1.1), ("eda", 1.0), ("python", 1.0)]),
            ("Research Analyst", [("hypothesis_testing", 1.2), ("r", 1.0), ("experimental_design", 1.0)]),
            ("Business Analyst", [("excel", 1.2), ("communication", 1.0), ("eda", 0.9)]),
            ("Data Science Intern", [("python", 1.1), ("ml_basics", 1.1), ("statistics", 1.3)]),
        ],
    },
    {
        "key": "bsc_isys", "name": "B.Sc Information Systems", "degree": "B.Sc",
        "aliases": ["B.Sc Information Systems"],
        "skills": [("systems_analysis", "core*"), "requirements", "dbms", "sql",
                   "software_engineering", "bpa", "erp", "eda", "project_management", "it_management",
                   "documentation", "communication", ("teamwork", "enh")],
        "roles": [
            ("Business Analyst", [("bpa", 1.2), ("requirements", 1.2), ("sql", 1.0), ("communication", 1.1)]),
            ("Systems Analyst", [("systems_analysis", 1.3), ("requirements", 1.3), ("sql", 1.0)]),
            ("IT Analyst", [("systems_analysis", 1.1), ("it_management", 1.0), ("sql", 1.0)]),
            ("ERP Support Analyst", [("erp", 1.3), ("sql", 1.0), ("troubleshooting", 0.9)]),
            ("Application Support Engineer", [("troubleshooting", 1.2), ("sql", 1.1), ("documentation", 0.9)]),
        ],
    },
    {
        "key": "bsc_iot", "name": "B.Sc IoT / Internet of Things", "degree": "B.Sc",
        "aliases": ["B.Sc Internet of Things"],
        "skills": [("iot", "core*"), ("embedded", "core"), "c", "cpp", "python", "esp32", "arduino",
                   "sensors", "actuators", "mqtt", "rest_api", "networks", "cloud_iot",
                   "edge_computing", "data_collection", "microcontrollers"],
        "roles": [
            ("IoT Developer Intern", [("iot", 1.3), ("embedded", 1.1), ("mqtt", 1.0), ("python", 1.0)]),
            ("Embedded Systems Intern", [("embedded", 1.3), ("microcontrollers", 1.1), ("c", 1.1)]),
            ("IoT Solutions Intern", [("iot", 1.2), ("cloud_iot", 1.0), ("networks", 0.9)]),
            ("Edge Computing Intern", [("edge_computing", 1.3), ("esp32", 1.0), ("python", 1.0)]),
        ],
    },
    {
        "key": "bsc_blockchain", "name": "B.Sc Blockchain Technology", "degree": "B.Sc",
        "aliases": ["B.Sc Blockchain"],
        "skills": [("blockchain", "core*"), ("cryptography", "core"), "ethereum", "solidity",
                   "smart_contracts", "web3", "javascript", "nodejs", "blockchain_security",
                   "consensus", ("system_design", "enh")],
        "roles": [
            ("Blockchain Developer Intern", [("solidity", 1.3), ("smart_contracts", 1.2), ("ethereum", 1.1)]),
            ("Smart Contract Developer", [("solidity", 1.3), ("blockchain_security", 1.1), ("smart_contracts", 1.3)]),
            ("Web3 Developer Intern", [("web3", 1.3), ("javascript", 1.1), ("react", 0.9)]),
        ],
    },
    {
        "key": "bsc_ca", "name": "B.Sc Computer Applications", "degree": "B.Sc",
        "aliases": ["BSc Computer Applications"],
        "skills": [("programming_fundamentals", "core"), "c", "cpp", "java", "python", "dsa",
                   "dbms", "sql", ("html", "core"), ("css", "enh"), ("javascript", "core"),
                   "os", "networks", "software_engineering", "git"],
        "roles": [
            ("Application Developer", [("oop", 1.2), ("java", 1.0), ("sql", 1.0), ("javascript", 1.0)]),
            ("Software Developer", [("dsa", 1.2), ("python", 1.0), ("sql", 1.0), ("git", 0.9)]),
            ("Web Developer", [("html", 1.2), ("css", 1.1), ("javascript", 1.2)]),
            ("Database Developer", [("sql", 1.3), ("dbms", 1.2), ("database_design", 1.0)]),
            ("IT Support Engineer", [("it_support", 1.2), ("troubleshooting", 1.1), ("networks", 1.0)]),
        ],
    },
    {
        "key": "bsc_ct", "name": "B.Sc Computer Technology", "degree": "B.Sc",
        "aliases": ["BSc Computer Technology"],
        "skills": [("programming_fundamentals", "core"), "computer_architecture", "os", "networks",
                   "dbms", "sql", "dsa", ("html", "enh"), ("javascript", "enh"),
                   "software_engineering", "linux", "git", ("cybersecurity", "enh")],
        "roles": [
            ("Software Developer", [("dsa", 1.2), ("sql", 1.0), ("programming_fundamentals", 1.2)]),
            ("IT Support Engineer", [("it_support", 1.3), ("troubleshooting", 1.2), ("os", 1.0)]),
            ("Network Support Engineer", [("networks", 1.3), ("tcp_ip", 1.1), ("linux", 1.0)]),
            ("Web Developer", [("html", 1.2), ("javascript", 1.1), ("css", 1.0)]),
            ("System Administrator Intern", [("sysadmin", 1.3), ("linux", 1.2), ("os", 1.0)]),
        ],
    },
    {
        "key": "bsc_phy_cs", "name": "B.Sc Physical Science with Computer Science", "degree": "B.Sc",
        "aliases": ["B.Sc Physical Science with Computer Applications", "B.Sc PCM/PCS Computer Science"],
        "skills": [("mathematics", "core"), ("physics", "core"), ("programming_fundamentals", "core"),
                   "python", "cpp", "dsa", "dbms", "sql", "networks", ("html", "enh"),
                   ("javascript", "enh"), "eda", "statistics", ("ml_basics", "enh"),
                   ("cybersecurity", "enh")],
        "roles": [
            ("Data Analyst", [("sql", 1.2), ("python", 1.1), ("eda", 1.0), ("statistics", 1.0)]),
            ("Software Developer Intern", [("programming_fundamentals", 1.2), ("python", 1.0), ("git", 0.9)]),
            ("Research Assistant", [("statistics", 1.2), ("python", 1.0), ("documentation", 0.9)]),
            ("IT Support", [("it_support", 1.2), ("troubleshooting", 1.1), ("networks", 1.0)]),
            ("Web Developer", [("html", 1.2), ("javascript", 1.1), ("css", 1.0)]),
            ("Technical Analyst", [("eda", 1.1), ("excel", 1.0), ("sql", 1.0)]),
        ],
    },
]

# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------

def _skill_entry(entry) -> dict:
    code, tier = entry if isinstance(entry, tuple) else (entry, "spec")
    if code not in CATALOG:
        raise KeyError(f"catalog missing canonical skill code '{code}'")
    label, category, aliases, default_w = CATALOG[code]
    return {
        "code": code,
        "label": label,
        "category": category,
        "aliases": list(aliases),
        "demand_weight": W[tier],
    }


def _validate(stream: dict, skills: list[dict]) -> None:
    codes = [s["code"] for s in skills]
    if len(codes) != len(set(codes)):
        raise ValueError(f"{stream['key']}: duplicate skill codes in stream")
    if len(codes) < 8:
        raise ValueError(f"{stream['key']}: too few skills ({len(codes)})")
    labels = [s["label"].lower() for s in skills]
    if len(labels) != len(set(labels)):
        raise ValueError(f"{stream['key']}: duplicate skill labels (synonym risk)")
    code_set = set(codes)
    for role_name, required in stream["roles"]:
        for code, _w in required:
            if code not in code_set:
                raise ValueError(f"{stream['key']}: role '{role_name}' requires unknown code '{code}'")
        if not (3 <= len(required) <= 7):
            raise ValueError(f"{stream['key']}: role '{role_name}' has {len(required)} required skills")


def build_all() -> None:
    streams_meta = []
    for stream in STREAMS:
        # Auto-add role-required skills the stream list omits, at the
        # industry-enhancement tier (roles demand them for jobs even when the
        # academic programme does not teach them).
        codes = {e if isinstance(e, str) else e[0] for e in stream["skills"]}
        for _role, required in stream["roles"]:
            for code, _w in required:
                if code not in codes:
                    stream["skills"].append((code, "enh"))
                    codes.add(code)
        skills = [_skill_entry(e) for e in stream["skills"]]
        _validate(stream, skills)
        cfg = {
            "key": stream["key"],
            "name": stream["name"],
            "degree": stream["degree"],
            "skills": skills,
            "target_roles": [
                {"name": name, "required": [{"code": c, "weight": w} for c, w in req]}
                for name, req in stream["roles"]
            ],
            "learning_resources": {
                code: RESOURCES[code]
                for code in (e if isinstance(e, str) else e[0] for e in stream["skills"])
                if code in RESOURCES
            },
        }
        out = CONFIGS / f"stream_{stream['key']}.json"
        out.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {out.name}: {len(skills)} skills, {len(stream['roles'])} roles")
        streams_meta.append({
            "key": stream["key"],
            "name": stream["name"],
            "degree": stream["degree"],
            "aliases": stream["aliases"],
        })

    # streams.json: keep existing cse/ece first (unchanged names, add degree),
    # then append the new academic streams.
    existing = json.loads((CONFIGS / "streams.json").read_text(encoding="utf-8"))
    kept = []
    for s in existing["streams"]:
        row = {"key": s["key"], "name": s["name"]}
        if s["key"] == "cse":
            row["degree"] = "B.Tech / B.E."
            row["aliases"] = ["Computer Science & Engineering", "CSE"]
        elif s["key"] == "ece":
            row["degree"] = "B.Tech / B.E."
            row["aliases"] = ["Electronics & Communication Engineering", "ECE"]
        kept.append(row)
    (CONFIGS / "streams.json").write_text(
        json.dumps({"streams": kept + streams_meta}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"streams.json now lists {len(kept) + len(streams_meta)} streams")


if __name__ == "__main__":
    build_all()
