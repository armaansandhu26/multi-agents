#!/usr/bin/env python3
"""Build and verify the hardened SQL problem bank (offline).

Adds rich fixtures + candidate problems, tags legacy items as tier=easy,
and verifies every gold query discriminates wrong naive queries.

Usage:
    python scripts/build_sql_bank.py          # verify only
    python scripts/build_sql_bank.py --write  # rewrite sql.json + sql_fixtures.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.execution_grading import build_fixture_db, _execute_select

FIXTURES_PATH = ROOT / "data" / "problems" / "sql_fixtures.json"
SQL_PATH = ROOT / "data" / "problems" / "sql.json"

# ---------------------------------------------------------------------------
# New fixtures (larger datasets, traps: cancelled rows, price snapshots, ties)
# ---------------------------------------------------------------------------

NEW_FIXTURES = {
    "ecommerce_orders": {
        "description": "Online store. order_items.sale_price is the price at checkout (may differ from products.list_price). Only status='completed' orders count as sales unless the question says otherwise.",
        "schema": [
            "CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT, signup_date TEXT)",
            "CREATE TABLE categories (category_id INTEGER PRIMARY KEY, name TEXT)",
            "CREATE TABLE products (product_id INTEGER PRIMARY KEY, name TEXT, category_id INTEGER, list_price REAL)",
            "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT, status TEXT)",
            "CREATE TABLE order_items (item_id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, sale_price REAL)",
        ],
        "inserts": [
            "INSERT INTO categories VALUES (1,'Electronics'),(2,'Books'),(3,'Home')",
            "INSERT INTO products VALUES (1,'Phone',1,699.0),(2,'Tablet',1,399.0),(3,'SQL Guide',2,45.0),(4,'Novel',2,18.0),(5,'Lamp',3,32.0),(6,'Rug',3,120.0),(7,'Monitor',1,899.0)",
            "INSERT INTO customers VALUES (1,'Ada','2021-03-01'),(2,'Ben','2022-01-15'),(3,'Cleo','2020-11-20'),(4,'Dan','2023-06-01'),(5,'Eve','2019-08-10')",
            "INSERT INTO orders VALUES (1,1,'2023-01-10','completed'),(2,1,'2023-02-14','cancelled'),(3,2,'2023-01-20','completed'),(4,2,'2023-03-05','completed'),(5,3,'2023-02-01','completed'),(6,3,'2023-04-12','pending'),(7,4,'2023-05-01','completed'),(8,5,'2023-01-05','cancelled'),(9,5,'2023-06-15','completed'),(10,1,'2023-05-20','completed'),(11,2,'2023-01-25','completed'),(12,2,'2023-01-28','completed')",
            "INSERT INTO order_items VALUES (1,1,1,1,679.0),(2,1,3,2,42.0),(3,2,1,1,699.0),(4,3,4,3,17.0),(5,3,3,1,45.0),(6,4,5,2,30.0),(7,4,6,1,115.0),(8,5,2,1,389.0),(9,5,5,1,32.0),(10,7,3,1,45.0),(11,9,4,1,18.0),(12,10,2,1,379.0),(13,10,5,1,32.0),(14,11,4,2,17.0),(15,12,4,1,18.0)",
        ],
    },
    "clinic_records": {
        "description": "Clinic scheduling and billing. appointment status is scheduled, completed, or no_show. Only completed visits count unless stated otherwise.",
        "schema": [
            "CREATE TABLE patients (patient_id INTEGER PRIMARY KEY, name TEXT, birth_year INTEGER)",
            "CREATE TABLE doctors (doctor_id INTEGER PRIMARY KEY, name TEXT, specialty TEXT)",
            "CREATE TABLE appointments (appt_id INTEGER PRIMARY KEY, patient_id INTEGER, doctor_id INTEGER, appt_date TEXT, status TEXT)",
            "CREATE TABLE diagnoses (code TEXT PRIMARY KEY, description TEXT)",
            "CREATE TABLE appointment_diagnoses (appt_id INTEGER, code TEXT)",
            "CREATE TABLE prescriptions (rx_id INTEGER PRIMARY KEY, appt_id INTEGER, drug_name TEXT, days_supply INTEGER)",
        ],
        "inserts": [
            "INSERT INTO patients VALUES (1,'Mia',1988),(2,'Noah',1995),(3,'Olivia',1990),(4,'Paul',1979),(5,'Quinn',2001)",
            "INSERT INTO doctors VALUES (1,'Dr Adams','GP'),(2,'Dr Brooks','GP'),(3,'Dr Chen','Cardiology'),(4,'Dr Diaz','Dermatology')",
            "INSERT INTO appointments VALUES (1,1,1,'2023-01-10','completed'),(2,1,1,'2023-02-15','completed'),(3,1,1,'2023-03-01','no_show'),(4,2,2,'2023-01-20','completed'),(5,2,2,'2023-01-22','completed'),(6,2,2,'2023-01-24','completed'),(7,2,3,'2023-02-05','completed'),(8,3,3,'2023-01-25','completed'),(9,3,4,'2023-03-10','completed'),(10,4,1,'2023-02-28','scheduled'),(11,5,2,'2023-05-01','completed'),(12,5,4,'2023-05-15','completed'),(13,4,3,'2023-06-01','no_show'),(14,3,3,'2023-06-10','completed')",
            "INSERT INTO diagnoses VALUES ('J06','URI'),('I10','Hypertension'),('L30','Dermatitis'),('Z00','Checkup')",
            "INSERT INTO appointment_diagnoses VALUES (1,'J06'),(2,'I10'),(4,'J06'),(5,'J06'),(6,'J06'),(7,'I10'),(8,'I10'),(9,'L30'),(11,'Z00'),(12,'L30')",
            "INSERT INTO prescriptions VALUES (1,1,'Amoxicillin',7),(2,2,'Lisinopril',30),(3,4,'Amoxicillin',7),(4,5,'Amoxicillin',7),(5,6,'Amoxicillin',7),(6,7,'Metoprolol',30),(7,8,'Hydrocortisone',14),(8,11,'Multivitamin',90),(9,12,'Hydrocortisone',14)",
        ],
    },
    "project_tasks": {
        "description": "Engineering tasks with assignees and hour logs. A task may have multiple assignees; logged hours can exceed estimates.",
        "schema": [
            "CREATE TABLE projects (project_id INTEGER PRIMARY KEY, name TEXT, budget_hours INTEGER, active INTEGER)",
            "CREATE TABLE tasks (task_id INTEGER PRIMARY KEY, project_id INTEGER, title TEXT, estimate_hours INTEGER)",
            "CREATE TABLE employees (employee_id INTEGER PRIMARY KEY, name TEXT, team TEXT)",
            "CREATE TABLE task_assignments (task_id INTEGER, employee_id INTEGER, role TEXT)",
            "CREATE TABLE time_logs (log_id INTEGER PRIMARY KEY, task_id INTEGER, employee_id INTEGER, hours REAL, log_date TEXT)",
        ],
        "inserts": [
            "INSERT INTO projects VALUES (1,'Apollo',120,1),(2,'Borealis',80,1),(3,'Catalyst',60,0)",
            "INSERT INTO tasks VALUES (1,1,'Design API',40),(2,1,'Build API',60),(3,1,'Write docs',20),(4,2,'Migrate DB',50),(5,2,'Cutover',30),(6,3,'Archive',10)",
            "INSERT INTO employees VALUES (1,'Riley','Platform'),(2,'Sam','Platform'),(3,'Taylor','Data'),(4,'Jordan','Data'),(5,'Casey','Platform')",
            "INSERT INTO task_assignments VALUES (1,1,'owner'),(1,2,'reviewer'),(2,1,'owner'),(2,2,'owner'),(3,5,'owner'),(4,3,'owner'),(4,1,'owner'),(4,4,'owner'),(5,3,'owner'),(6,4,'owner')",
            "INSERT INTO time_logs VALUES (1,1,1,24,'2023-01-05'),(2,1,2,8,'2023-01-06'),(3,2,1,35,'2023-01-10'),(4,2,2,40,'2023-01-12'),(5,3,5,12,'2023-01-15'),(6,4,3,30,'2023-02-01'),(7,4,1,15,'2023-02-02'),(8,4,4,28,'2023-02-03'),(9,5,3,20,'2023-02-10'),(10,2,1,10,'2023-01-20'),(11,1,1,5,'2023-01-21')",
        ],
    },
}

EC_SCHEMA = """Database schema (SQLite):

Table customers(customer_id, name, signup_date)
Table categories(category_id, name)
Table products(product_id, name, category_id, list_price)
Table orders(order_id, customer_id, order_date, status) -- status: completed, cancelled, pending
Table order_items(item_id, order_id, product_id, quantity, sale_price) -- sale_price at checkout; may differ from list_price

Only count orders with status='completed' as sales unless the question explicitly says otherwise."""

CL_SCHEMA = """Database schema (SQLite):

Table patients(patient_id, name, birth_year)
Table doctors(doctor_id, name, specialty)
Table appointments(appt_id, patient_id, doctor_id, appt_date, status) -- scheduled, completed, no_show
Table diagnoses(code, description)
Table appointment_diagnoses(appt_id, code)
Table prescriptions(rx_id, appt_id, drug_name, days_supply)

Only count appointments with status='completed' unless the question explicitly says otherwise."""

PT_SCHEMA = """Database schema (SQLite):

Table projects(project_id, name, budget_hours, active) -- active: 1=yes, 0=no
Table tasks(task_id, project_id, title, estimate_hours)
Table employees(employee_id, name, team)
Table task_assignments(task_id, employee_id, role)
Table time_logs(log_id, task_id, employee_id, hours, log_date)"""

NEW_CANDIDATES = [
    {
        "id": "ec_q1",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": True,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: For each customer, compute total revenue from completed orders (sum of quantity * sale_price across all line items). Return two columns: customer name, total revenue — ordered by total revenue descending, then name ascending. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT c.name, SUM(oi.quantity * oi.sale_price) AS revenue FROM customers c JOIN orders o ON o.customer_id = c.customer_id JOIN order_items oi ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY c.customer_id ORDER BY revenue DESC, c.name ASC",
        "wrong_queries": [
            "SELECT c.name, SUM(oi.quantity * oi.sale_price) AS revenue FROM customers c JOIN orders o ON o.customer_id = c.customer_id JOIN order_items oi ON oi.order_id = o.order_id GROUP BY c.customer_id ORDER BY revenue DESC, c.name ASC",
        ],
    },
    {
        "id": "ec_q2",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: Which category name(s) have the highest total completed-order revenue (include ties)? Revenue is quantity * sale_price summed over completed orders only. Return one column: category name. Write a single SQLite SELECT statement.",
        "gold_query": "WITH cat_rev AS (SELECT cat.name, SUM(oi.quantity * oi.sale_price) AS rev FROM categories cat JOIN products p ON p.category_id = cat.category_id JOIN order_items oi ON oi.product_id = p.product_id JOIN orders o ON o.order_id = oi.order_id WHERE o.status = 'completed' GROUP BY cat.category_id) SELECT name FROM cat_rev WHERE rev = (SELECT MAX(rev) FROM cat_rev)",
        "wrong_queries": [],
    },
    {
        "id": "ec_q3",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: Find customer name(s) who have purchased at least one completed-order product from EVERY category in the database (include customers with purchases in all three categories). Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT c.name FROM customers c WHERE NOT EXISTS (SELECT 1 FROM categories cat WHERE NOT EXISTS (SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id = o.order_id JOIN products p ON p.product_id = oi.product_id WHERE o.customer_id = c.customer_id AND o.status = 'completed' AND p.category_id = cat.category_id))",
        "wrong_queries": [],
    },
    {
        "id": "ec_q4",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: Find product name(s) that never appear in any line item belonging to a completed order (products with zero completed sales). Return one column: product name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT p.name FROM products p WHERE NOT EXISTS (SELECT 1 FROM order_items oi JOIN orders o ON o.order_id = oi.order_id WHERE oi.product_id = p.product_id AND o.status = 'completed')",
        "wrong_queries": [],
    },
    {
        "id": "ec_q5",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: For each category, find the product name(s) with the highest total quantity sold in completed orders (include ties within a category). Return two columns: category name, product name. Write a single SQLite SELECT statement.",
        "gold_query": "WITH sales AS (SELECT cat.name AS category, p.name AS product, SUM(oi.quantity) AS qty FROM categories cat JOIN products p ON p.category_id = cat.category_id JOIN order_items oi ON oi.product_id = p.product_id JOIN orders o ON o.order_id = oi.order_id WHERE o.status = 'completed' GROUP BY cat.category_id, p.product_id), mx AS (SELECT category, MAX(qty) AS max_qty FROM sales GROUP BY category) SELECT s.category, s.product FROM sales s JOIN mx ON mx.category = s.category AND mx.max_qty = s.qty",
        "wrong_queries": [],
    },
    {
        "id": "ec_q6",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: Find customer name(s) whose average completed-order total (sum of line items per order) is strictly greater than the average completed-order total across ALL completed orders in the database. Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "WITH order_totals AS (SELECT o.order_id, o.customer_id, SUM(oi.quantity * oi.sale_price) AS total FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY o.order_id), cust_avg AS (SELECT customer_id, AVG(total) AS avg_order FROM order_totals GROUP BY customer_id) SELECT c.name FROM customers c JOIN cust_avg ca ON ca.customer_id = c.customer_id WHERE ca.avg_order > (SELECT AVG(total) FROM order_totals)",
        "wrong_queries": [],
    },
    {
        "id": "ec_q7",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: Which calendar month (format YYYY-MM) had the highest total completed-order revenue? If tied, return all tied months. Return one column: month. Write a single SQLite SELECT statement.",
        "gold_query": "WITH monthly AS (SELECT substr(o.order_date, 1, 7) AS month, SUM(oi.quantity * oi.sale_price) AS rev FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE o.status = 'completed' GROUP BY month) SELECT month FROM monthly WHERE rev = (SELECT MAX(rev) FROM monthly)",
        "wrong_queries": [],
    },
    {
        "id": "ec_q8",
        "db_id": "ecommerce_orders",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{EC_SCHEMA}\n\nQuestion: Find customer name(s) who bought product 'Phone' and product 'Lamp' in completed orders (not necessarily the same order). Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT c.name FROM customers c WHERE EXISTS (SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id = o.order_id JOIN products p ON p.product_id = oi.product_id WHERE o.customer_id = c.customer_id AND o.status = 'completed' AND p.name = 'Phone') AND EXISTS (SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id = o.order_id JOIN products p ON p.product_id = oi.product_id WHERE o.customer_id = c.customer_id AND o.status = 'completed' AND p.name = 'Lamp')",
        "wrong_queries": [],
    },
    {
        "id": "cl_q1",
        "db_id": "clinic_records",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{CL_SCHEMA}\n\nQuestion: Find doctor name(s) whose count of completed appointments is strictly greater than the average count of completed appointments per doctor. Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "WITH doc_counts AS (SELECT d.doctor_id, d.name, COUNT(*) AS n FROM doctors d JOIN appointments a ON a.doctor_id = d.doctor_id WHERE a.status = 'completed' GROUP BY d.doctor_id) SELECT name FROM doc_counts WHERE n > (SELECT AVG(n) FROM doc_counts)",
        "wrong_queries": [],
    },
    {
        "id": "cl_q2",
        "db_id": "clinic_records",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{CL_SCHEMA}\n\nQuestion: Find patient name(s) with completed appointments in at least 3 distinct calendar months (month = YYYY-MM from appt_date). Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT p.name FROM patients p JOIN appointments a ON a.patient_id = p.patient_id WHERE a.status = 'completed' GROUP BY p.patient_id HAVING COUNT(DISTINCT substr(a.appt_date, 1, 7)) >= 3",
        "wrong_queries": [],
    },
    {
        "id": "cl_q3",
        "db_id": "clinic_records",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{CL_SCHEMA}\n\nQuestion: Find diagnosis description(s) that appear on completed appointments handled by at least 2 different doctor specialties. Return one column: description. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT d.description FROM diagnoses d JOIN appointment_diagnoses ad ON ad.code = d.code JOIN appointments a ON a.appt_id = ad.appt_id JOIN doctors doc ON doc.doctor_id = a.doctor_id WHERE a.status = 'completed' GROUP BY d.code HAVING COUNT(DISTINCT doc.specialty) >= 2",
        "wrong_queries": [],
    },
    {
        "id": "cl_q4",
        "db_id": "clinic_records",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{CL_SCHEMA}\n\nQuestion: Find patient name(s) who have at least one no_show appointment that occurs AFTER a completed appointment with the same doctor. Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT DISTINCT p.name FROM patients p JOIN appointments ns ON ns.patient_id = p.patient_id JOIN appointments done ON done.patient_id = p.patient_id AND done.doctor_id = ns.doctor_id WHERE ns.status = 'no_show' AND done.status = 'completed' AND ns.appt_date > done.appt_date",
        "wrong_queries": [],
    },
    {
        "id": "cl_q5",
        "db_id": "clinic_records",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{CL_SCHEMA}\n\nQuestion: Find drug name(s) prescribed on the largest number of distinct completed appointments (include ties). Count distinct appt_id only for completed appointments linked through prescriptions. Return one column: drug_name. Write a single SQLite SELECT statement.",
        "gold_query": "WITH rx_counts AS (SELECT pr.drug_name, COUNT(DISTINCT pr.appt_id) AS n FROM prescriptions pr JOIN appointments a ON a.appt_id = pr.appt_id WHERE a.status = 'completed' GROUP BY pr.drug_name) SELECT drug_name FROM rx_counts WHERE n = (SELECT MAX(n) FROM rx_counts)",
        "wrong_queries": [],
    },
    {
        "id": "cl_q6",
        "db_id": "clinic_records",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{CL_SCHEMA}\n\nQuestion: Find patient name(s) who have at least one scheduled appointment but zero completed appointments. Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT p.name FROM patients p WHERE EXISTS (SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id AND a.status = 'scheduled') AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id AND a.status = 'completed')",
        "wrong_queries": [],
    },
    {
        "id": "pt_q1",
        "db_id": "project_tasks",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{PT_SCHEMA}\n\nQuestion: Find active project name(s) where total logged hours across all tasks exceed the project's budget_hours. Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT p.name FROM projects p JOIN tasks t ON t.project_id = p.project_id JOIN time_logs tl ON tl.task_id = t.task_id WHERE p.active = 1 GROUP BY p.project_id HAVING SUM(tl.hours) > p.budget_hours",
        "wrong_queries": [],
    },
    {
        "id": "pt_q2",
        "db_id": "project_tasks",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{PT_SCHEMA}\n\nQuestion: Find employee name(s) assigned as owner to at least one task in every ACTIVE project (active=1). Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT e.name FROM employees e WHERE NOT EXISTS (SELECT 1 FROM projects p WHERE p.active = 1 AND NOT EXISTS (SELECT 1 FROM tasks t JOIN task_assignments ta ON ta.task_id = t.task_id WHERE t.project_id = p.project_id AND ta.employee_id = e.employee_id AND ta.role = 'owner'))",
        "wrong_queries": [],
    },
    {
        "id": "pt_q3",
        "db_id": "project_tasks",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{PT_SCHEMA}\n\nQuestion: Find task title(s) whose total logged hours exceed their estimate_hours. Return two columns: project name, task title. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT p.name, t.title FROM projects p JOIN tasks t ON t.project_id = p.project_id JOIN time_logs tl ON tl.task_id = t.task_id GROUP BY t.task_id HAVING SUM(tl.hours) > t.estimate_hours",
        "wrong_queries": [],
    },
    {
        "id": "pt_q4",
        "db_id": "project_tasks",
        "tier": "candidate",
        "order_matters": True,
        "prompt": f"{PT_SCHEMA}\n\nQuestion: For each team, return the employee name with the highest total logged hours on that team (include ties). Return two columns: team, employee name — ordered by team ascending. Write a single SQLite SELECT statement.",
        "gold_query": "WITH team_hours AS (SELECT e.team, e.name, SUM(tl.hours) AS hrs FROM employees e JOIN time_logs tl ON tl.employee_id = e.employee_id GROUP BY e.employee_id), mx AS (SELECT team, MAX(hrs) AS max_hrs FROM team_hours GROUP BY team) SELECT th.team, th.name FROM team_hours th JOIN mx ON mx.team = th.team AND mx.max_hrs = th.hrs ORDER BY th.team ASC",
        "wrong_queries": [],
    },
    {
        "id": "pt_q5",
        "db_id": "project_tasks",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{PT_SCHEMA}\n\nQuestion: Find project name(s) where no task has any logged hours by an employee outside the Platform team. (Projects where every logged hour is by Platform employees, and at least one hour was logged.) Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT p.name FROM projects p WHERE EXISTS (SELECT 1 FROM tasks t JOIN time_logs tl ON tl.task_id = t.task_id JOIN employees e ON e.employee_id = tl.employee_id WHERE t.project_id = p.project_id) AND NOT EXISTS (SELECT 1 FROM tasks t JOIN time_logs tl ON tl.task_id = t.task_id JOIN employees e ON e.employee_id = tl.employee_id WHERE t.project_id = p.project_id AND e.team <> 'Platform')",
        "wrong_queries": [],
    },
    {
        "id": "pt_q6",
        "db_id": "project_tasks",
        "tier": "candidate",
        "order_matters": False,
        "prompt": f"{PT_SCHEMA}\n\nQuestion: Find employee name(s) who logged hours on more than one distinct project. Return one column: name. Write a single SQLite SELECT statement.",
        "gold_query": "SELECT e.name FROM employees e JOIN time_logs tl ON tl.employee_id = e.employee_id JOIN tasks t ON t.task_id = tl.task_id GROUP BY e.employee_id HAVING COUNT(DISTINCT t.project_id) > 1",
        "wrong_queries": [],
    },
]


def verify_candidate(problem: dict, fixtures: dict) -> list[str]:
    errors = []
    db_id = problem["db_id"]
    gold = problem["gold_query"]
    fixture = fixtures[db_id]
    order_matters = problem.get("order_matters", False)

    try:
        rows = _execute_select(build_fixture_db(fixture), gold)
    except Exception as exc:
        return [f"gold query error: {exc}"]

    if not rows:
        errors.append("gold query returned no rows")

    gold_rows = rows

    def rows_match(candidate_sql: str) -> bool:
        try:
            cand_rows = _execute_select(build_fixture_db(fixture), candidate_sql)
        except Exception:
            return False
        if cand_rows and gold_rows and len(cand_rows[0]) != len(gold_rows[0]):
            return False
        if order_matters:
            return cand_rows == gold_rows
        return sorted(map(repr, cand_rows)) == sorted(map(repr, gold_rows))

    if not rows_match(gold):
        errors.append("gold query self-check failed")

    for wrong in problem.get("wrong_queries", []):
        if rows_match(wrong):
            errors.append(f"naive wrong query incorrectly passed: {wrong[:80]}...")

    return errors


def load_legacy_easy() -> list[dict]:
    with SQL_PATH.open() as f:
        legacy = json.load(f)
    for item in legacy:
        item["tier"] = "easy"
        item.pop("wrong_queries", None)
    return legacy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write updated JSON files")
    args = parser.parse_args()

    with FIXTURES_PATH.open() as f:
        fixtures = json.load(f)
    merged_fixtures = {**fixtures, **NEW_FIXTURES}

    failures = 0
    print(f"Verifying {len(NEW_CANDIDATES)} candidate problems...")
    for problem in NEW_CANDIDATES:
        errors = verify_candidate(problem, merged_fixtures)
        if errors:
            failures += 1
            print(f"  FAIL {problem['id']}: {'; '.join(errors)}")
        else:
            rows = _execute_select(
                build_fixture_db(merged_fixtures[problem["db_id"]]), problem["gold_query"]
            )
            print(f"  ok   {problem['id']}: {len(rows)} rows")

    if failures:
        print(f"\n{failures} candidate(s) failed verification")
        sys.exit(1)

    if not args.write:
        print("\nVerification passed. Re-run with --write to update JSON files.")
        return

    with FIXTURES_PATH.open("w") as f:
        json.dump(merged_fixtures, f, indent=2)
        f.write("\n")

    bank = load_legacy_easy()
    for item in NEW_CANDIDATES:
        entry = {k: v for k, v in item.items() if k != "wrong_queries"}
        entry["source"] = "Spider-style (curated, hardened)"
        bank.append(entry)

    with SQL_PATH.open("w") as f:
        json.dump(bank, f, indent=2)
        f.write("\n")

    print(f"\nWrote {len(merged_fixtures)} fixtures and {len(bank)} SQL problems "
          f"({len(NEW_CANDIDATES)} new candidates, {len(bank) - len(NEW_CANDIDATES)} easy legacy).")


if __name__ == "__main__":
    main()
