-- ============================================================
-- Phase 1 Infrastructure Optimization: HNSW Vector Indexing
-- Upgrades vector cosine similarity from linear scan to O(log N) HNSW search
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_skills_hnsw ON skills USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_sp_hnsw ON student_profiles USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_jd_hnsw ON job_descriptions USING hnsw (embedding vector_cosine_ops);
