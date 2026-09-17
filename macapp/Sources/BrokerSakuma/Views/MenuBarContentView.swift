import AppKit
import Foundation
import SwiftUI

/// Spec section 40: the menu-bar app surfaces status and the safety
/// controls (Pause / Resume / Emergency Stop) without opening the full
/// dashboard window.
struct MenuBarContentView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.openWindow) private var openWindow
    @Environment(\.openURL) private var openURL
    @State private var showEmergencyStopConfirmation = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("DominusBot").font(.headline)
                Spacer()
                StatusBadge(state: appState.dashboard?.systemState ?? .unknown, displayMode: .simple)
            }

            if let dashboard = appState.dashboard {
                Text("Capital: \(dashboard.capitalOperationalUsd, format: .currency(code: "USD"))")
                Text("P&L hoje: \(dashboard.dailyPnlUsd, format: .currency(code: "USD"))")
            } else {
                Text("Sem conexão com o sistema")
                    .foregroundStyle(.secondary)
            }

            Divider()

            // Grouped so this VStack's own child count stays well under
            // ViewBuilder's per-block limit as items get added here.
            Group {
                Button("Abrir DominusBot") {
                    openWindow(id: "dashboard")
                }

                Button("Configurações") {
                    openWindow(id: "settings")
                }

                Button("Abrir painel no navegador") {
                    openURL(APIClient.defaultBaseURL.appendingPathComponent("dashboard"))
                }

                Button("Pausar") {
                    Task { await appState.sendSystemAction(.pause) }
                }

                Button("Retomar") {
                    Task { await appState.sendSystemAction(.resume) }
                }

                Button("🛑 Parada de Emergência") {
                    showEmergencyStopConfirmation = true
                }
                .foregroundStyle(.red)
            }

            Divider()

            Button("Sair") {
                NSApplication.shared.terminate(nil)
            }
        }
        .padding(14)
        .frame(width: 260)
        .confirmationDialog(
            "Tem certeza que deseja acionar a Parada de Emergência?",
            isPresented: $showEmergencyStopConfirmation,
            titleVisibility: .visible
        ) {
            Button("Confirmar Parada de Emergência", role: .destructive) {
                Task { await appState.sendSystemAction(.killSwitch) }
            }
            Button("Cancelar", role: .cancel) {}
        } message: {
            Text("Isso bloqueia novas operações, novos bots e transferências até ser reiniciado manualmente.")
        }
    }
}
