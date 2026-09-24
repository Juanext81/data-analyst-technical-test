# Requirements Document

## Introduction

This feature delivers an end-to-end e-commerce dataset project for a data analyst technical test. It defines a relational PostgreSQL schema, generates reproducible sample data (including intentional data-quality issues for cleaning exercises), hosts the database in AWS, connects the repository to the AWS database, and provides analysis queries.

The project already contains an initial `schema.sql` (five tables: customers, categories, products, orders, order_details) and a `README.md`. The `generate_data.py` and `queries.sql` files described in the README do not yet exist and must be created. This spec extends the existing schema, adds a data-generation script that injects realistic data-quality defects, provisions an AWS-hosted PostgreSQL database, wires the repository to that database, and delivers analysis queries.

## Glossary

- **Dataset_Generator**: The Python script (`generate_data.py`) that produces the sample CSV files.
- **Schema_Definition**: The SQL file (`schema.sql`) that defines the database tables and relationships.
- **AWS_Database**: The PostgreSQL database instance provisioned in AWS (Amazon RDS for PostgreSQL) that hosts the schema and data.
- **Repository_Connection**: The configuration and connection code that allows scripts in the repository to connect to the AWS_Database.
- **Data_Loader**: The process or script that loads the generated CSV files into the AWS_Database.
- **Data_Quality_Defect**: An intentionally introduced NULL value or inconsistent value in the generated data for the analyst to detect and handle.
- **Order_Detail_Row**: A single line item in the `order_details` table linking one order to one product.
- **Last_12_Months**: The time window spanning from 12 months before the generation date up to the generation date.
- **COP**: Colombian pesos, the currency used for price values.

## Requirements

### Requirement 1: Database Schema Definition

**User Story:** As a data analyst, I want a well-defined relational e-commerce schema, so that I can store customers, products, categories, orders, and order line items with referential integrity.

#### Acceptance Criteria

1. THE Schema_Definition SHALL define a `customers` table with columns `customer_id` as primary key, `first_name` (maximum 50 characters), `last_name` (maximum 50 characters), `email` (maximum 100 characters), `city` (maximum 50 characters), and `registration_date` as a date value.
2. THE Schema_Definition SHALL define `customer_id`, `first_name`, `last_name`, and `email` in the `customers` table as mandatory (non-null) columns, and SHALL enforce `email` uniqueness across all customer rows.
3. THE Schema_Definition SHALL define a `categories` table with columns `category_id` as primary key and `category_name` (maximum 50 characters), where `category_id` and `category_name` are mandatory (non-null) columns.
4. THE Schema_Definition SHALL define a `products` table with columns `product_id` as primary key, `product_name` (maximum 100 characters), `category_id`, `price`, and `stock`, where `product_id`, `product_name`, `category_id`, and `price` are mandatory (non-null) columns.
5. THE Schema_Definition SHALL define an `orders` table with columns `order_id` as primary key, `customer_id`, `order_date` as a date value, `status` (maximum 20 characters), and `payment_method` (maximum 30 characters), where `order_id`, `customer_id`, and `order_date` are mandatory (non-null) columns.
6. THE Schema_Definition SHALL define an `order_details` table with columns `order_detail_id` as primary key, `order_id`, `product_id`, `quantity`, and `unit_price`, where `order_detail_id`, `order_id`, `product_id`, `quantity`, and `unit_price` are mandatory (non-null) columns.
7. THE Schema_Definition SHALL declare a foreign key from `products.category_id` to `categories.category_id`.
8. THE Schema_Definition SHALL declare a foreign key from `orders.customer_id` to `customers.customer_id`.
9. THE Schema_Definition SHALL declare a foreign key from `order_details.order_id` to `orders.order_id`.
10. THE Schema_Definition SHALL declare a foreign key from `order_details.product_id` to `products.product_id`.
11. THE Schema_Definition SHALL store `price` and `unit_price` as fixed-point numeric values with a scale of exactly 2 decimal places and a total precision of 12 digits, supporting values from 0.00 to 9,999,999,999.99.
12. IF a `price`, `unit_price`, `quantity`, or `stock` value less than 0 is submitted, THEN THE Schema_Definition SHALL reject the row and preserve the existing table contents unchanged, returning an error indicating a constraint violation.

### Requirement 2: Sample Data Volume

**User Story:** As a data analyst, I want a sample dataset of realistic size, so that my analysis queries return meaningful aggregate results.

#### Acceptance Criteria

1. THE Dataset_Generator SHALL generate exactly 30 customer records, each with a unique customer identifier.
2. THE Dataset_Generator SHALL generate exactly 4 category records, each with a unique category identifier.
3. THE Dataset_Generator SHALL generate exactly 15 product records, with each of the 4 categories assigned at least 1 product.
4. THE Dataset_Generator SHALL generate exactly 100 order records, each referencing an existing customer identifier.
5. THE Dataset_Generator SHALL generate exactly 250 Order_Detail_Row records, each referencing an existing order identifier and an existing product identifier.
6. THE Dataset_Generator SHALL assign each product to exactly one of the 4 categories via a valid category identifier.
7. WHERE a fixed random seed is configured, THE Dataset_Generator SHALL produce byte-identical output across repeated runs.
8. IF any generated foreign key value (customer, category, order, or product identifier) does not reference an existing parent record, THEN THE Dataset_Generator SHALL fail generation and produce an error indicating the referential integrity violation without writing partial output.
9. THE Dataset_Generator SHALL assign every registration date and order date a value within the 12 months (365 days) preceding the generation date, inclusive.

### Requirement 3: Date Distribution

**User Story:** As a data analyst, I want dates spread across the last 12 months, so that I can analyze monthly trends over a realistic time window.

#### Acceptance Criteria

1. THE Dataset_Generator SHALL assign each customer `registration_date` a value within the 365 days preceding the generation date, inclusive.
2. THE Dataset_Generator SHALL assign each order `order_date` a value within the 365 days preceding the generation date, inclusive.
3. THE Dataset_Generator SHALL distribute `order_date` values so that every one of the 12 calendar months in the window contains at least one order and no single calendar month contains more than 40 percent of all orders.
4. WHEN an order references a customer, THE Dataset_Generator SHALL assign the order an `order_date` on or after that customer's `registration_date` and on or before the generation date.
5. IF a customer's `registration_date` is within the current (most recent) calendar month such that no valid order date range remains before the generation date, THEN THE Dataset_Generator SHALL still assign that customer's orders an `order_date` on or after the registration_date and on or before the generation date.

### Requirement 4: Intentional Data-Quality Defects

**User Story:** As a data analyst, I want a few intentional NULL and inconsistent values in the dataset, so that I can practice detecting and cleaning realistic data-quality issues.

#### Acceptance Criteria

1. THE Dataset_Generator SHALL introduce at least 1 and no more than the per-table cap of Data_Quality_Defect values into the generated dataset.
2. THE Dataset_Generator SHALL introduce at least one NULL value in a nullable non-key column.
3. THE Dataset_Generator SHALL introduce at least one inconsistent value, defined as a value that deviates from the expected format, unit, or casing of other values in the same column (for example, mixed-case city names or a differently formatted email).
4. THE Dataset_Generator SHALL limit Data_Quality_Defect values to no more than 10 percent of rows in any single table, rounded down, with a minimum of at least 1 defect placed in the dataset overall.
5. THE Dataset_Generator SHALL NOT introduce Data_Quality_Defect values into primary key columns or foreign key columns.
6. THE Dataset_Generator SHALL record each introduced Data_Quality_Defect in a summary output identifying the table, column, row identifier, and defect type.
7. WHERE a fixed random seed is configured, THE Dataset_Generator SHALL introduce the same Data_Quality_Defect values at the same locations across repeated runs.

### Requirement 5: Historical Price Accuracy

**User Story:** As a data analyst, I want order line items to retain the price at the time of purchase, so that historical revenue figures stay accurate even if a product price changes later.

#### Acceptance Criteria

1. WHEN an Order_Detail_Row is generated, THE Dataset_Generator SHALL set `unit_price` to a value exactly equal to the referenced product's `price` at generation time, expressed with 2 decimal places within the range 0.01 to 9,999,999,999.99.
2. IF the product referenced by an Order_Detail_Row cannot be resolved or has no defined `price` at generation time, THEN THE Dataset_Generator SHALL reject the row, exclude it from the generated dataset, and produce an error indication identifying the unresolved product reference, without altering any previously generated rows.
3. WHEN a product's `price` changes after an Order_Detail_Row has been generated, THE Dataset_Generator SHALL leave the previously stored `unit_price` of that Order_Detail_Row unchanged.

### Requirement 6: CSV Export

**User Story:** As a data analyst, I want the generated data exported as CSV files, so that I can inspect it and load it into the database.

#### Acceptance Criteria

1. THE Dataset_Generator SHALL write exactly five CSV files named for the five tables: categories, products, customers, orders, and order_details.
2. THE Dataset_Generator SHALL write the CSV files to a `data/` directory.
3. THE Dataset_Generator SHALL include a header row containing the column names of the corresponding table as the first line of each CSV file.
4. IF the `data/` directory does not exist, THEN THE Dataset_Generator SHALL create the `data/` directory before writing files.
5. WHEN the Dataset_Generator runs and CSV files from a previous run already exist, THE Dataset_Generator SHALL overwrite them with the current run's output.
6. IF writing any CSV file fails, THEN THE Dataset_Generator SHALL report an error identifying the file that could not be written.

### Requirement 7: AWS Database Provisioning

**User Story:** As a data analyst, I want the database hosted in AWS, so that the schema and data live in a managed, accessible PostgreSQL instance.

#### Acceptance Criteria

1. THE AWS_Database SHALL be a PostgreSQL instance provisioned on Amazon RDS that reaches the "available" state and accepts client connections on its configured port.
2. WHEN the Schema_Definition is applied to the AWS_Database, THE AWS_Database SHALL contain exactly the five tables (customers, categories, products, orders, order_details) and their four foreign key relationships (products.category_id → categories, orders.customer_id → customers, order_details.order_id → orders, order_details.product_id → products).
3. IF applying the Schema_Definition fails on any table or foreign key relationship, THEN THE feature SHALL report an error indicating which statement failed and leave the AWS_Database without partially applied objects from the failed run.
4. THE feature SHALL provide provisioning documentation that includes: the RDS instance identifier and PostgreSQL engine version, the network accessibility settings required to connect (publicly accessible flag and the security group inbound rule allowing the PostgreSQL port), and the ordered commands to create the schema and load the data.
5. WHERE connection credentials are required, THE feature SHALL store the credentials outside of version-controlled source files and reference them by name rather than embedding their values.

### Requirement 8: Repository-to-Database Connection

**User Story:** As a data analyst, I want the repository connected to the AWS database, so that I can load data and run queries against the hosted instance from the project.

#### Acceptance Criteria

1. THE Repository_Connection SHALL read AWS_Database connection parameters (host, port, database name, user, password) from a configuration source that is excluded from version control tracking.
2. WHEN valid connection parameters are provided, THE Repository_Connection SHALL establish a connection to the AWS_Database within 10 seconds and expose a confirmed connection state that allows queries to be executed.
3. IF one or more connection parameters (host, port, database name, user, or password) are missing or invalid, THEN THE Repository_Connection SHALL not establish a connection and SHALL return an error identifying each missing or invalid parameter by name.
4. IF all parameters are present but a connection cannot be established within 10 seconds (host unreachable or authentication rejected by AWS_Database), THEN THE Repository_Connection SHALL not establish a connection and SHALL return an error indicating the connection attempt failed and its cause.
5. THE feature SHALL provide a template configuration file listing the required connection parameter names (host, port, database name, user, password) with placeholder values and no real credential values.

### Requirement 9: Data Loading into AWS

**User Story:** As a data analyst, I want the generated CSV data loaded into the AWS database, so that I can query the hosted dataset.

#### Acceptance Criteria

1. THE Data_Loader SHALL load the five CSV files from the `data/` directory into the corresponding tables in the AWS_Database and confirm completion once all rows are loaded.
2. THE Data_Loader SHALL load tables in an order that satisfies foreign key dependencies: categories and customers before products and orders, and products and orders before order_details.
3. WHEN a CSV cell is empty (contains no characters between delimiters) for a nullable column, THE Data_Loader SHALL insert a NULL value for that cell rather than an empty string.
4. IF a foreign key constraint is violated during loading, THEN THE Data_Loader SHALL report the violating table and row identifier and SHALL not leave the target table partially loaded from the failed file.
5. IF any CSV source file is missing from the `data/` directory, THEN THE Data_Loader SHALL report an error identifying the missing file and SHALL not begin loading.
6. WHEN loading completes, THE Data_Loader SHALL verify that each table's loaded row count matches the source CSV row count and report any mismatch.

### Requirement 10: Documentation

**User Story:** As a data analyst, I want the project documented, so that I can reproduce the setup from schema creation through AWS hosting and analysis.

#### Acceptance Criteria

1. THE README SHALL document the command(s) to generate the sample data, including any prerequisites, and how the reader confirms the CSV files were produced.
2. THE README SHALL document the ordered steps to provision the AWS_Database and connect to it, including the required connection parameters and where to supply them.
3. THE README SHALL document the ordered steps to load the CSV data into the AWS_Database, including the required load order.
4. THE README SHALL document the command(s) to run the Analysis_Queries and how to confirm they executed.
5. THE README SHALL document each intentional Data_Quality_Defect with its affected entity, defect type, and how to distinguish it from an unintended error.
6. IF any required setup step (generate, provision, connect, load, or query) is not documented, THEN the documentation SHALL be considered incomplete for review purposes.
