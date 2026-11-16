-- Chay trong Supabase -> SQL Editor (1 lan). Backend dung ddl-auto=validate nen bang phai co san.
create schema if not exists app;
create table app.users (
  id bigint generated always as identity primary key,
  username varchar(32) not null unique, full_name varchar(80) not null,
  password_hash varchar(100) not null,
  role varchar(10) not null default 'user' check (role in ('admin','user')),
  permissions varchar(100) not null default '',
  active boolean not null default true, must_change boolean not null default false,
  created_at timestamptz not null default now());
create table app.devices (
  device_id varchar(40) primary key check (device_id ~ '^[A-Za-z0-9_-]{1,40}$'),
  name varchar(80) not null, location varchar(120),
  status varchar(10) not null default 'PENDING' check (status in ('PENDING','ACTIVE','DISABLED','RETIRED')),
  online boolean not null default false, last_payload jsonb, last_seen timestamptz,
  created_at timestamptz not null default now());
create table app.alarm_events (
  id varchar(72) primary key,
  device_id varchar(40) not null references app.devices(device_id),
  kind varchar(4) not null check (kind in ('FIRE','GAS')),
  gas_adc int not null check (gas_adc between 0 and 4095),
  age_ms bigint not null default 0, received_at timestamptz not null default now());
create index on app.alarm_events (device_id, received_at desc);
create table app.audit_logs (
  id bigint generated always as identity primary key,
  occurred_at timestamptz not null default now(),
  actor varchar(32) not null, action varchar(32) not null, target varchar(80));
create table app.user_devices (
  user_id bigint not null references app.users(id) on delete cascade,
  device_id varchar(40) not null references app.devices(device_id) on delete cascade,
  granted_at timestamptz not null default now(), primary key (user_id, device_id));
insert into app.devices (device_id, name, status) values ('esp32-tang1', 'ESP32 tầng 1', 'ACTIVE');

-- Bao ve them: bat RLS, khong tao policy -> role anon/authenticated cua Supabase khong doc duoc.
alter table app.users        enable row level security;
alter table app.devices      enable row level security;
alter table app.alarm_events enable row level security;
alter table app.audit_logs   enable row level security;
alter table app.user_devices enable row level security;
