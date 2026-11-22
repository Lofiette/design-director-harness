# Поля нормализованного пилота

Источник — существующий data_contract.json 0.3.0. Это навигация для преобразования; новые бизнес-сущности или облегчённая конкурирующая схема не вводятся. Человек может передать исходные выгрузки без заполнения этих структур.

## source_batch

Обязательные поля: `source_batch_id`, `source_system_id`, `source_kind`, `source_locator`, `source_revision`, `source_schema_version`, `extracted_at`, `coverage_period`, `coverage_description`, `row_count`, `content_checksum`, `inventory_status`, `verification_status`, `access_scope`.

`null` допускается схемой: не предусмотрен для перечисленных полей.

## lineage

Обязательные поля: `source_batch_ids`, `source_record_ids`, `source_revision`, `source_schema_version`, `observed_at`, `ingested_at`, `transform_version`, `evidence_refs`.

`null` допускается схемой: не предусмотрен для перечисленных полей.

## measurement_population

Обязательные поля: `population_id`, `population_version`, `population_type`, `period`, `inclusion_rule`, `exclusion_rule`, `selection_method`, `member_set_ref`, `member_key_type`, `denominator_definition_version`, `known_denominator`, `denominator_unit`, `denominator_source_ref`, `coverage_status`, `coverage_limitations`, `lineage`.

`null` допускается схемой: `known_denominator`, `denominator_source_ref`.

## work_item

Обязательные поля: `work_item_id`, `parent_work_item_id`, `initiative_id`, `product_id`, `team_id`, `work_class`, `complexity_rule`, `complexity_class`, `dod_version`, `accepted_request_at`, `started_at`, `final_accepted_at`, `cancelled_at`, `current_state`, `calendar_id`, `lineage`.

`null` допускается схемой: `parent_work_item_id`, `product_id`, `complexity_class`, `started_at`, `final_accepted_at`, `cancelled_at`.

## work_event

Обязательные поля: `work_event_id`, `work_item_id`, `occurred_at`, `event_type`, `from_state`, `to_state`, `reason`, `lineage`.

`null` допускается схемой: `from_state`, `to_state`, `reason`.

## calendar

Обязательные поля: `calendar_id`, `calendar_version`, `timezone`, `effective_period`, `business_intervals`, `standard_day_hours`, `lineage`.

`null` допускается схемой: `standard_day_hours`.

## commitment

Обязательные поля: `commitment_id`, `work_item_id`, `baseline_snapshot_id`, `baseline_frozen_at`, `original_due_at`, `original_scope`, `original_dod_version`, `final_accepted_at`, `current_due_at`, `change_reason`, `cancelled_at`, `lineage`.

`null` допускается схемой: `final_accepted_at`, `current_due_at`, `change_reason`, `cancelled_at`.

## research_attempt

Обязательные поля: `attempt_id`, `study_id`, `participant_pseudonym_id`, `scenario_id`, `role_segment`, `variant_id`, `artifact_version`, `protocol_version`, `attempt_order`, `started_at`, `ended_at`, `pause_seconds`, `success`, `assisted`, `abandoned`, `critical_error`, `success_rule_version`, `error_rule_version`, `valid_attempt`, `invalid_reason`, `data_kind`, `observation_type`, `lineage`.

`null` допускается схемой: `ended_at`, `success`, `critical_error`, `invalid_reason`.

## research_question

Обязательные поля: `research_question_id`, `initiative_id`, `question`, `registered_at`, `evidence_ready_at`, `original_decision_due_at`, `owner_role`, `evidence_refs`, `lineage`.

`null` допускается схемой: `evidence_ready_at`.

## decision

Обязательные поля: `decision_id`, `initiative_id`, `research_question_ids`, `materiality_rule_version`, `is_material`, `evidence_refs`, `evidence_available_at`, `decision_at`, `decision_type`, `rationale`, `alternatives_considered`, `decision_owner_role`, `action_owner_role`, `revisit_condition`, `lineage`.

`null` допускается схемой: `evidence_available_at`, `action_owner_role`, `revisit_condition`.

