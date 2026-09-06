-- ============================================================
-- SIH26044 — Academia–Industry Collaboration Portal
-- Core schema. All config-driven taxonomy / RBAC / feedback-loop tables.
-- ============================================================

create extension if not exists vector;

-- ------------------------------------------------------------
-- RBAC: dynamic roles/permissions (editable without code change)
-- ------------------------------------------------------------
create table roles_permissions (
    id uuid primary key default gen_random_uuid(),
    name text unique not null,                -- 'student' | 'tpo' | 'industry' | 'admin'
    display_name text not null,
    permissions jsonb not null default '[]',  -- list of permission strings
    description text,
    updated_at timestamptz not null default now()
);

create table institutions (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    stream text not null,                     -- active stream key e.g. 'cse'
    city text,
    is_synthetic boolean not null default true,
    created_at timestamptz not null default now()
);

create table organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    industry text,
    is_synthetic boolean not null default true,
    created_at timestamptz not null default now()
);

create table users (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    full_name text not null,
    password_hash text not null,
    role_id uuid not null references roles_permissions(id),
    institution_id uuid references institutions(id),
    organization_id uuid references organizations(id),
    is_active boolean not null default true,
    consent_given boolean not null default false,
    consent_at timestamptz,
    created_at timestamptz not null default now()
);

create table rbac_audit_log (
    id uuid primary key default gen_random_uuid(),
    changed_by uuid references users(id),
    role_id uuid references roles_permissions(id),
    old_permissions jsonb,
    new_permissions jsonb,
    created_at timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Skill taxonomy (config-driven, per stream; embeddings in pgvector)
-- ------------------------------------------------------------
create table skills (
    id uuid primary key default gen_random_uuid(),
    stream text not null,
    code text not null,                       -- stable key e.g. 'cse.sql'
    label text not null,
    category text not null,
    aliases text[] not null default '{}',
    demand_weight numeric not null default 1.0 check (demand_weight >= 0.3 and demand_weight <= 3.0),
    embedding vector(384),
    embedding_provider text,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (stream, code)
);
create index idx_skills_stream on skills(stream);

create table learning_resources (
    id uuid primary key default gen_random_uuid(),
    stream text not null,
    skill_id uuid not null references skills(id) on delete cascade,
    title text not null,
    provider text not null,
    url text not null,
    duration_hours numeric not null default 4,
    is_free boolean not null default true,
    created_at timestamptz not null default now()
);
create index idx_learning_resources_skill on learning_resources(skill_id);

-- ------------------------------------------------------------
-- Student profiles
-- ------------------------------------------------------------
create table student_profiles (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null unique references users(id) on delete cascade,
    institution_id uuid references institutions(id),
    stream text not null default 'cse',
    resume_text text,
    resume_file_name text,
    cgpa numeric,
    graduation_year int,
    bio text,
    consent_given boolean not null default false,
    consent_at timestamptz,
    extraction_status text not null default 'pending',  -- pending|extracted|failed
    embedding vector(384),                    -- aggregate profile embedding (pgvector)
    embedding_provider text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index idx_student_profiles_embedding on student_profiles
    using ivfflat (embedding vector_cosine_ops) with (lists = 50);

-- Verification state machine per claimed skill:
--   claimed -> institution_cosigned -> verified
create table skill_verification_state (
    id uuid primary key default gen_random_uuid(),
    student_profile_id uuid not null references student_profiles(id) on delete cascade,
    skill_id uuid not null references skills(id),
    state text not null default 'claimed'
        check (state in ('claimed', 'institution_cosigned', 'verified')),
    extracted_from_resume boolean not null default false,
    claimed_at timestamptz not null default now(),
    claimed_by uuid references users(id),
    cosigned_at timestamptz,
    cosigned_by uuid references users(id),
    cosigned_note text,
    verified_at timestamptz,
    verified_by uuid references users(id),
    verified_note text,
    updated_at timestamptz not null default now(),
    unique (student_profile_id, skill_id)
);
create index idx_svs_student on skill_verification_state(student_profile_id);
create index idx_svs_state on skill_verification_state(state);

-- ------------------------------------------------------------
-- Job descriptions
-- ------------------------------------------------------------
create table job_descriptions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    posted_by_user_id uuid references users(id),
    title text not null,
    kind text not null default 'internship' check (kind in ('internship', 'placement')),
    stream text not null default 'cse',
    description text not null,
    location text,
    stipend int,
    salary_min int,
    salary_max int,
    seats int not null default 1,
    status text not null default 'open' check (status in ('open', 'closed')),
    extracted_skills jsonb not null default '[]',  -- [{skill_id, code, label, weight}]
    extraction_status text not null default 'pending',
    embedding vector(384),                    -- aggregate JD embedding (pgvector)
    embedding_provider text,
    is_synthetic boolean not null default true,
    created_at timestamptz not null default now()
);
create index idx_jd_embedding on job_descriptions
    using ivfflat (embedding vector_cosine_ops) with (lists = 50);
create index idx_jd_org on job_descriptions(organization_id);
create index idx_jd_stream on job_descriptions(stream);

-- ------------------------------------------------------------
-- Matches with explainability payload
-- ------------------------------------------------------------
create table matches (
    id uuid primary key default gen_random_uuid(),
    student_profile_id uuid not null references student_profiles(id) on delete cascade,
    job_description_id uuid not null references job_descriptions(id) on delete cascade,
    score numeric not null,
    semantic_score numeric,                   -- embedding-cosine component
    taxonomy_score numeric,                   -- taxonomy-overlap component
    provider text not null,                   -- 'fastembed' | 'tfidf'
    matched_skills jsonb not null default '[]',
    missing_skills jsonb not null default '[]',
    extra_skills jsonb not null default '[]',
    literal_keyword_overlap numeric not null default 0,  -- raw word overlap (explainability proof)
    created_at timestamptz not null default now(),
    unique (student_profile_id, job_description_id)
);
create index idx_matches_student on matches(student_profile_id);
create index idx_matches_job on matches(job_description_id);

-- ------------------------------------------------------------
-- Applications & outcomes
-- ------------------------------------------------------------
create table applications (
    id uuid primary key default gen_random_uuid(),
    student_profile_id uuid not null references student_profiles(id) on delete cascade,
    job_description_id uuid not null references job_descriptions(id) on delete cascade,
    match_id uuid references matches(id),
    status text not null default 'applied'
        check (status in ('applied', 'shortlisted', 'selected', 'rejected', 'withdrawn')),
    cover_note text,
    applied_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (student_profile_id, job_description_id)
);
create index idx_applications_jd on applications(job_description_id);

create table outcomes (
    id uuid primary key default gen_random_uuid(),
    application_id uuid not null unique references applications(id) on delete cascade,
    job_description_id uuid not null references job_descriptions(id),
    student_profile_id uuid not null references student_profiles(id),
    result text not null check (result in ('completed', 'dropped', 'hired')),
    performance_rating int check (performance_rating between 1 and 5),
    industry_feedback text,
    logged_by_user_id uuid references users(id),
    is_synthetic boolean not null default false,
    logged_at timestamptz not null default now()
);
create index idx_outcomes_jd on outcomes(job_description_id);

-- ------------------------------------------------------------
-- Outcome-feedback loop
-- ------------------------------------------------------------
create table skill_recalibration_log (
    id uuid primary key default gen_random_uuid(),
    outcome_id uuid not null references outcomes(id) on delete cascade,
    skill_id uuid not null references skills(id),
    old_weight numeric not null,
    new_weight numeric not null,
    reason text not null,
    created_at timestamptz not null default now()
);
create index idx_recal_skill on skill_recalibration_log(skill_id);

create table curriculum_gap_signal (
    id uuid primary key default gen_random_uuid(),
    institution_id uuid not null references institutions(id) on delete cascade,
    stream text not null,
    skill_id uuid not null references skills(id),
    gap_count int not null default 0,          -- students of the institution missing this skill vs open JD demand
    student_count int not null default 0,
    demand_score numeric not null default 0,   -- sum of demand_weight of JDs requiring it
    severity text not null default 'low',      -- low | medium | high
    detail jsonb not null default '{}',
    computed_at timestamptz not null default now()
);
create index idx_cgs_institution on curriculum_gap_signal(institution_id, stream);

-- ------------------------------------------------------------
-- Seed provenance (synthetic data labelling)
-- ------------------------------------------------------------
create table seed_runs (
    id uuid primary key default gen_random_uuid(),
    stream text not null,
    note text,
    is_synthetic boolean not null default true,
    created_at timestamptz not null default now()
);

-- Vector index (small dataset; ivfflat is enough)
create index idx_skills_embedding on skills
    using ivfflat (embedding vector_cosine_ops) with (lists = 50);
