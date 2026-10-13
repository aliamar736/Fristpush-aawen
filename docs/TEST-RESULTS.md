# نتائج الاختبارات

تاريخ التشغيل: 2026-10-13 — البيئة: Ubuntu 24.04، Python 3.13، PostgreSQL 16.15 + PostGIS 3.4، Redis 7، Node 22، Chromium (Playwright 1.56).
الملفات الخام: `backend.txt`, `backend-junit.xml`, `web-unit.txt`, `web-e2e.txt` في هذا المجلد.

## الملخص
| المجموعة | العدد | ناجح | فاشل | ملاحظات |
|---|---|---|---|---|
| الخادم (pytest، على PostgreSQL/PostGIS حقيقي) | 62 | 62 | 0 | تغطية الأسطر 83% (`apps/`) |
| الويب — فحص الأنواع (tsc strict) | — | ✅ | — | |
| الويب — وحدات (vitest) | 4 | 4 | 0 | المسودات وإعادة الإرسال دون تكرار |
| الويب — طرف إلى طرف (Playwright/Chromium) | 22 (+2 لقطات متخطاة) | 22 | 0 | يشمل فحص الوصول axe (WCAG 2 A/AA) |
| تطبيق Flutter | 1 | — | — | **لم يُشغَّل**: Flutter غير متاح في البيئة |
| صور Docker | — | — | — | **لم تُبنَ**: السجل محجوب؛ `docker compose config` صالح |

## سيناريوهات القسم 12 الإلزامية
| السيناريو | أين اختُبر | النتيجة |
|---|---|---|
| دورة البلاغ حتى التحقق والاعتراض وإعادة الفتح | `test_full_lifecycle_with_objection_and_recurrence`, `test_problem_returned_links_previous_fix…`, e2e field/staff | ✅ |
| عدم الإغلاق بمرور الوقت | `test_reports_never_close_because_time_passed` (تقديم الزمن 400 يوم) | ✅ |
| التوجيه على حدود المناطق وصلاحيات الجهات | `test_routing_permissions.py` (8 اختبارات) + e2e staff | ✅ |
| الإرسال المكرر بعد انقطاع الاتصال | `test_retry_with_same_client_id…`, `test_concurrent_duplicate_submissions…` (4 خيوط متزامنة)، `drafts.test.ts`، e2e offline | ✅ |
| انتهاء تنبيه الطريق وتجديده | `test_roadnow.py` (7 اختبارات) | ✅ |
| التنافس على آخر كمية مورد | `test_race_for_last_unit` (8 خيوط متزامنة: نجاح واحد و7 تعارض) | ✅ |
| الحجز والإلغاء والاستلام والإرجاع | `test_reserve_cancel_pickup_return_cycle`, `test_donation_stock…`, حجز المهام | ✅ |
| فشل الدفع وتكرار إشعاراته والاسترداد | `test_finance.py` (11 اختبارًا) + e2e المحاكي (3 إشعارات → تسجيل واحد) | ✅ |
| العربية وRTL والوصول وحالات الخطأ | `e2e/a11y-rtl.spec.ts` (16 اختبارًا) + `test_arabic_error_format` | ✅ |
| النسخ الاحتياطي والاستعادة | `test_backup_and_restore_roundtrip` (pg_dump حقيقي → قاعدة جديدة → مقارنة الصفوف، وكشف ملف تالف) | ✅ |

## اختبارات الخادم
| الملف | الاختبار | النتيجة |
|---|---|---|
| `test_accounts_ops` | test_otp_login_flow_and_lockout | ✅ |
| `test_accounts_ops` | test_otp_not_exposed_in_production | ✅ |
| `test_accounts_ops` | test_sessions_list_and_revoke | ✅ |
| `test_accounts_ops` | test_account_deletion_anonymises_but_keeps_civic_record | ✅ |
| `test_accounts_ops` | test_first_admin_bootstrap_is_safe | ✅ |
| `test_accounts_ops` | test_demo_seed_refused_when_not_allowed | ✅ |
| `test_accounts_ops` | test_demo_rows_are_flagged_and_purgeable | ✅ |
| `test_accounts_ops` | test_health_and_public_config | ✅ |
| `test_finance` | test_pledge_is_not_a_payment_and_needs_approved_initiative | ✅ |
| `test_finance` | test_payment_success_with_duplicate_webhooks_books_once | ✅ |
| `test_finance` | test_bad_signature_and_amount_mismatch | ✅ |
| `test_finance` | test_payment_failure_keeps_pledge_and_allows_retry | ✅ |
| `test_finance` | test_refund_flow_approval_and_duplicate_refund_webhook | ✅ |
| `test_finance` | test_transfer_screenshot_is_not_payment_until_matched | ✅ |
| `test_finance` | test_disbursement_separation_of_duties_and_balance | ✅ |
| `test_finance` | test_requester_cannot_approve_own_disbursement | ✅ |
| `test_finance` | test_ledger_is_immutable_at_database_level | ✅ |
| `test_finance` | test_live_payments_disabled_until_configured | ✅ |
| `test_finance` | test_no_person_to_person_wallet_endpoints | ✅ |
| `test_inventory_community` | test_reserve_cancel_pickup_return_cycle | ✅ |
| `test_inventory_community` | test_donation_stock_is_consumed_and_not_returned | ✅ |
| `test_inventory_community` | test_task_booking_capacity_attendance_completion | ✅ |
| `test_inventory_community` | test_skills_profile_recommendations | ✅ |
| `test_inventory_community` | test_blocking_needs_and_help_offer_lifecycle | ✅ |
| `test_inventory_community` | test_initiative_approval_by_independent_coordinator | ✅ |
| `test_inventory_community` | test_proposal_review_and_budget_constrained_voting | ✅ |
| `test_inventory_community` | test_food_surplus_disabled_until_enabled | ✅ |
| `test_inventory_community` | test_coverage_dashboard_and_survey_assignment | ✅ |
| `test_inventory_community` | test_care_points_only_verified_are_public | ✅ |
| `test_inventory_community` | test_bundle_keeps_individual_report_status | ✅ |
| `test_offline_and_privacy` | test_retry_with_same_client_id_returns_same_report | ✅ |
| `test_offline_and_privacy` | test_public_view_hides_reporter_and_unverified_description | ✅ |
| `test_offline_and_privacy` | test_media_private_until_moderated_and_blur | ✅ |
| `test_offline_and_privacy` | test_upload_strips_exif_and_rejects_bad_files | ✅ |
| `test_offline_and_privacy` | test_arabic_error_format | ✅ |
| `test_report_lifecycle` | test_full_lifecycle_with_objection_and_recurrence | ✅ |
| `test_report_lifecycle` | test_problem_returned_links_previous_fix_and_requires_evidence | ✅ |
| `test_report_lifecycle` | test_reports_never_close_because_time_passed | ✅ |
| `test_report_lifecycle` | test_ai_cannot_change_status_or_close | ✅ |
| `test_report_lifecycle` | test_report_accepted_without_ai | ✅ |
| `test_report_lifecycle` | test_unresolvable_requires_reason_and_coordinator | ✅ |
| `test_report_lifecycle` | test_similar_reports_and_confirm_instead_of_duplicate | ✅ |
| `test_report_lifecycle` | test_priority_not_driven_by_votes_alone | ✅ |
| `test_report_lifecycle` | test_observed_time_separate_and_not_in_future | ✅ |
| `test_roadnow` | test_alert_expires_and_still_there_renews | ✅ |
| `test_roadnow` | test_max_lifetime_caps_renewals | ✅ |
| `test_roadnow` | test_road_open_votes_clear_alert | ✅ |
| `test_roadnow` | test_agency_staff_clears_immediately_and_marks_official | ✅ |
| `test_roadnow` | test_delayed_submission_not_published_as_live | ✅ |
| `test_roadnow` | test_rules_are_configurable | ✅ |
| `test_roadnow` | test_no_fabricated_traffic_metrics_and_emergency_is_separate | ✅ |
| `test_routing_permissions` | test_area_specific_rule_overrides_city_rule | ✅ |
| `test_routing_permissions` | test_point_near_boundary_with_different_agencies_needs_review | ✅ |
| `test_routing_permissions` | test_point_near_boundary_same_agency_is_auto | ✅ |
| `test_routing_permissions` | test_point_outside_coverage_needs_review | ✅ |
| `test_routing_permissions` | test_area_scoped_reviewer_cannot_act_outside_area | ✅ |
| `test_routing_permissions` | test_agency_portal_only_shows_own_referrals | ✅ |
| `test_routing_permissions` | test_only_sysadmin_grants_roles_and_changes_are_audited | ✅ |
| `test_routing_permissions` | test_category_admin_and_new_category_routes | ✅ |
| `test_accounts_ops` | test_backup_and_restore_roundtrip | ✅ |
| `test_inventory_community` | test_race_for_last_unit | ✅ |
| `test_offline_and_privacy` | test_concurrent_duplicate_submissions_create_one_report | ✅ |

## اختبارات الواجهة (Playwright)
```
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: / (2.1s)
✓ e2e/finance-field.spec.ts:5:1 › pledge → simulated payment with duplicate webhooks → counted once (3.7s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /map (2.5s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /report/new (2.5s)
✓ e2e/finance-field.spec.ts:28:1 › field worker attaches completion proof; resident independently verifies (5.7s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /aawen (2.2s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /aawen?tab=store (2.0s)
✓ e2e/report-flow.spec.ts:23:1 › citizen submits a report through the wizard and lands on its tracking page (2.3s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /contribute (2.2s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /login (1.7s)
✓ e2e/report-flow.spec.ts:37:1 › report written offline is queued, then sent exactly once when the connection returns (4.5s)
✓ e2e/report-flow.spec.ts:55:1 › a resident confirms an existing nearby report instead of filing a duplicate (2.5s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /reports/1 (3.3s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /proposals (2.0s)
✓ e2e/a11y-rtl.spec.ts:9:3 › no serious accessibility violations: /initiatives/1 (2.4s)
✓ e2e/staff.spec.ts:7:1 › reviewer verifies and refers a report; agency acknowledges separately (6.8s)
✓ e2e/staff.spec.ts:35:1 › a citizen cannot open the staff console (1.8s)
✓ e2e/a11y-rtl.spec.ts:18:1 › staff console passes accessibility checks (9.5s)
✓ e2e/a11y-rtl.spec.ts:30:1 › Arabic RTL by default, English switch flips direction (503ms)
✓ e2e/a11y-rtl.spec.ts:42:1 › five tabs and the report button are reachable by keyboard (457ms)
✓ e2e/a11y-rtl.spec.ts:50:1 › large text (200%) on a small phone does not cause horizontal scrolling (780ms)
✓ e2e/a11y-rtl.spec.ts:59:1 › error, empty and offline states (1.9s)
```
