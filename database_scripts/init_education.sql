-- Education Database Schema
-- Iranian Education Organization

CREATE TABLE IF NOT EXISTS organization_units (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    unit_type VARCHAR(50) NOT NULL,
    parent_id INTEGER REFERENCES organization_units(id),
    province VARCHAR(100),
    city VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    national_id VARCHAR(10) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    organization_unit_id INTEGER REFERENCES organization_units(id),
    position VARCHAR(100),
    hire_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS salary_items (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    base_salary DECIMAL(15,2),
    allowances DECIMAL(15,2),
    deductions DECIMAL(15,2),
    net_salary DECIMAL(15,2),
    payment_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ranking_requests (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    request_date DATE NOT NULL,
    ranking_type VARCHAR(50),
    current_rank VARCHAR(50),
    requested_rank VARCHAR(50),
    status VARCHAR(20) DEFAULT 'pending',
    review_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS retirement_records (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    retirement_date DATE NOT NULL,
    retirement_type VARCHAR(50),
    years_of_service INTEGER,
    pension_amount DECIMAL(15,2),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schools (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    school_type VARCHAR(50),
    organization_unit_id INTEGER REFERENCES organization_units(id),
    capacity INTEGER,
    established_year INTEGER,
    address TEXT,
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    national_id VARCHAR(10) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    school_id INTEGER REFERENCES schools(id),
    grade VARCHAR(20),
    enrollment_year INTEGER,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sample Data

INSERT INTO organization_units (name, unit_type, parent_id, province, city) VALUES
('وزارت آموزش و پرورش', 'ministry', NULL, 'تهران', 'تهران'),
('اداره کل آموزش و پرورش تهران', 'province', 1, 'تهران', 'تهران'),
('اداره کل آموزش و پرورش اصفهان', 'province', 1, 'اصفهان', 'اصفهان'),
('منطقه آموزشی یک تهران', 'district', 2, 'تهران', 'تهران'),
('منطقه آموزشی دو تهران', 'district', 2, 'تهران', 'تهران'),
('منطقه آموزشی یک اصفهان', 'district', 3, 'اصفهان', 'اصفهان');

INSERT INTO employees (national_id, first_name, last_name, organization_unit_id, position, hire_date, status) VALUES
('0012345678', 'علی', 'احمدی', 4, 'مدیر مدرسه', '2010-09-01', 'active'),
('0023456789', 'فاطمه', 'محمدی', 4, 'دبیر ریاضی', '2012-03-15', 'active'),
('0034567890', 'محمد', 'رضایی', 5, 'دبیر فیزیک', '2008-09-01', 'active'),
('0045678901', 'زهرا', 'کریمی', 5, 'دبیر شیمی', '2015-01-10', 'active'),
('0056789012', 'حسین', 'مرتضوی', 6, 'دبیر ادبیات', '2005-09-01', 'active'),
('0067890123', 'مریم', 'فتحی', 4, 'دبیر زبان انگلیسی', '2018-06-20', 'active'),
('0078901234', 'رضا', 'نوری', 5, 'دبیر تربیت بدنی', '2020-02-15', 'active'),
('0089012345', 'سارا', '잠', 6, 'دبیر علوم', '2019-09-01', 'inactive');

INSERT INTO salary_items (employee_id, year, month, base_salary, allowances, deductions, net_salary, payment_date) VALUES
(1, 1403, 1, 45000000, 15000000, 5000000, 55000000, '1403-01-28'),
(1, 1403, 2, 45000000, 15000000, 5000000, 55000000, '1403-02-28'),
(2, 1403, 1, 38000000, 12000000, 4000000, 46000000, '1403-01-28'),
(2, 1403, 2, 38000000, 12000000, 4000000, 46000000, '1403-02-28'),
(3, 1403, 1, 42000000, 14000000, 5500000, 50500000, '1403-01-28'),
(4, 1403, 1, 36000000, 11000000, 3500000, 43500000, '1403-01-28'),
(5, 1403, 1, 50000000, 18000000, 7000000, 61000000, '1403-01-28'),
(6, 1403, 1, 32000000, 10000000, 3000000, 39000000, '1403-01-28');

INSERT INTO ranking_requests (employee_id, request_date, ranking_type, current_rank, requested_rank, status, review_date) VALUES
(1, '1403-01-15', 'ارتقای رتبه', 'کارشناس', 'کارشناس ارشد', 'approved', '1403-02-01'),
(2, '1403-02-01', 'ارتقای رتبه', 'معلم', 'معلم درجه ۲', 'pending', NULL),
(3, '1402-11-20', 'ارتقای رتبه', 'کارشناس ارشد', 'سرپرست', 'rejected', '1403-01-10'),
(5, '1403-01-05', 'ارتقای رتبه', 'معلم درجه ۱', 'معلم درجه ۲', 'approved', '1403-01-20');

INSERT INTO retirement_records (employee_id, retirement_date, retirement_type, years_of_service, pension_amount, reason) VALUES
(8, '1403-03-01', 'بازنشستگی عادی', 25, 35000000, 'بازنشستگی پس از ۲۵ سال خدمت'),
(5, '1404-06-01', 'بازنشستگی پیش از موعد', 30, 42000000, 'بازنشستگی درخواستی');

INSERT INTO schools (name, school_type, organization_unit_id, capacity, established_year, address, phone) VALUES
('دبیرستان شهید بهشتی', 'دبیرستان', 4, 400, 1370, 'تهران، خیابان ولیعصر، کوچه ۱۲', '021-88776655'),
('دبیرستان فرزانگان', 'دبیرستان', 4, 350, 1385, 'تهران، خیابان آزادی، پلاک ۴۵', '021-66443322'),
('دبیرستان امام خمینی', 'دبیرستان', 5, 380, 1365, 'تهران، خیابان انقلاب، کوچه ۸', '021-77554433'),
('دبیرستان نمونه دولتی اصفهان', 'دبیرستان', 6, 300, 1380, 'اصفهان، خیابان چهارباغ، پلاک ۱۲۳', '031-33221100'),
('دبیرستان شاهد', 'دبیرستان', 4, 250, 1390, 'تهران، خیابان نبرد، کوچه ۵', '021-77889900');

INSERT INTO students (national_id, first_name, last_name, school_id, grade, enrollment_year, status) VALUES
('1012345678', 'امیر', 'سعیدی', 1, 'دهم', 1401, 'active'),
('1023456789', 'نیلوفر', 'شریفی', 1, 'یازدهم', 1400, 'active'),
('1034567890', 'پوریا', 'هاشمی', 2, 'دهم', 1401, 'active'),
('1045678901', 'الناز', 'جعفری', 2, 'دوازدهم', 1399, 'active'),
('1056789012', 'مهدی', 'سلیمانی', 3, 'یازدهم', 1400, 'active'),
('1067890123', 'یاسمن', 'بهرامی', 3, 'دهم', 1401, 'active'),
('1078901234', 'آرش', 'قاسمی', 4, 'دوازدهم', 1399, 'active'),
('1089012345', 'مهسا', 'abdollahi', 4, 'یازدهم', 1400, 'active'),
('1090123456', 'امید', 'خسروی', 5, 'دهم', 1401, 'active'),
('1101234567', 'زینب', 'رحمانی', 5, 'یازدهم', 1400, 'active');
