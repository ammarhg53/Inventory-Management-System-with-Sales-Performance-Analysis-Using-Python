# Inventory-Management-System-with-Sales-Performance-Analysis-Using-Python
This project is a Streamlit-based Inventory Management and Point of Sale (POS) System developed entirely using Python, designed to simulate a real-world retail / ERP-style application.  The system helps manage products, inventory, sales transactions, users, and performance analytics, while also demonstrating the use of data structures,
📌 Project Overview

This project is a Streamlit-based Inventory Management and Point of Sale (POS) System developed entirely using Python, designed to simulate a real-world retail / ERP-style application.

The system helps manage products, inventory, sales transactions, users, and performance analytics, while also demonstrating the use of data structures, algorithms, and business logic commonly used in modern retail software.

It is built with a strong focus on:

Practical usability

Academic clarity

Realistic business workflows

Clean separation of logic and UI

🎯 Objectives

Efficiently manage product inventory and stock levels

Perform sales operations through a POS interface

Track sales performance, staff activity, and time-based metrics

Apply algorithms for forecasting, optimization, fraud detection, and analysis

Provide a professional, responsive UI using Streamlit

Maintain data integrity and role-based access control

🧠 Key Features
🔐 Role-Based Access Control

Admin – Full system access, settings, analytics, and user management

Manager – Sales analysis, stock monitoring, approvals

POS Operator – Billing and transaction handling

Inventory Manager – Product management and restocking

📦 Inventory Management

Add, update, delete, and restock products

Category-based product organization

Low-stock alerts with visual indicators

Real-time stock updates after sales

🧾 Point of Sale (POS)

Product selection with quantity control

Automatic bill calculation

Multiple payment modes (Cash, UPI QR, Card – demo simulation)

Receipt generation (PDF) with bill number and transaction details

Customer details capture (name, mobile, email)

💳 UPI QR Payment (Demo)

QR code generated using standard UPI format

Dynamic amount and transaction note

Countdown timer with auto-expiry

Manual transaction ID validation for demo purposes

⚠️ Note: This is a demo simulation, not a real payment gateway integration.

📊 Sales & Performance Analysis

Daily, monthly, and yearly sales reports

Product-wise and category-wise analysis

Staff performance comparison

Peak sales hour analysis

Profit and revenue insights

🧮 Algorithms & Concepts Used

This project intentionally incorporates core Computer Science and ERP-related algorithms, including:

Moving Average Demand Forecasting (Basic Predictive Analytics)

Economic Order Quantity (EOQ) for inventory optimization

Linear Search, Binary Search, and Hash-based Search comparison

Trie-based product name suggestion (simulated)

Rule-based billing optimization and offers

Statistical Fraud Detection (Outlier Detection)

Queue (FIFO) simulation for POS flow

Stack-based Undo / Rollback mechanism

SHA-256 hashing for secure transaction logs

Sales ranking and recommendation algorithms

🎨 UI / UX Design

Built entirely using Streamlit

Custom CSS for a modern, ERP-style interface

Responsive layout with cards, tabs, and visual indicators

Light / Dark mode support

Clear color coding for stock status and alerts

All UI enhancements are additive only and do not modify business logic.

🛠️ Tech Stack

Language: Python

Framework: Streamlit

Database: SQLite

Libraries:

pandas

numpy

matplotlib

qrcode

hashlib

🚀 How to Run the Project
pip install streamlit
streamlit run app.py


Make sure Python 3.x is installed and the project folder is opened correctly.

🎓 Academic Relevance

This project is suitable for:

Engineering / BCA / BSc / Diploma students

Data Structures & Algorithms demonstration

Python application development

ERP / POS system concepts

Final-year or semester projects

It emphasizes clarity, correctness, and real-world relevance over unnecessary complexity.

⚠️ Disclaimer

Payment systems (UPI/Card) are simulated for demo and learning purposes

No real financial transactions are performed

Dummy/demo data (if enabled) is isolated from real data

👤 Author

Ammar Husain Gheewala
📍 India
🎓 Student | Python & ERP System Enthusiast
