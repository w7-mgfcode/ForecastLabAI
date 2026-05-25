"""Batch runner slice — portfolio forecasting orchestration (PRP-33).

One ``batch_job`` row fans out into N ``batch_job_item`` rows; each item is
executed sequentially by delegating to ``JobService.create_job`` via a lazy
in-method import. The MVP exposes zero mutating agent tools; downstream
PRPs (parallel-execution, priority-queue, export-and-retry,
champion-and-heatmap) consume the forward-compat columns on these tables
without schema changes.
"""
