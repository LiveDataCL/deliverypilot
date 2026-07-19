# driver-app

Flutter app for the driver ("repartidor") role. Scaffolded (`flutter create`),
toolchain-verified end to end on a physical device; the actual Fase 1 checklist
(login, foreground GPS service, lista de entregas, cambios de estado, push FCM)
is not yet built. See `deliverypilot-spec-claude-code.md` §5 Fase 1.

- **Package / applicationId:** `cl.livedata.deliverypilot.driver`
- **Display name:** DeliveryPilot Repartidor
- **Local dev:** `flutter run` on a connected device — day-to-day hot-reload
  development happens locally.
- **APK builds:** `.github/workflows/build-apk.yml` builds a debug APK in CI
  (GitHub Actions), since this machine's limited RAM can't reliably run a
  local Gradle build (see `docs/digital-debt.md`'s "Local Gradle builds OOM
  on this machine" entry). Signed release APKs are Fase 1 checklist item 9,
  not done yet — see `docs/build-apk.md`.
