import Foundation
import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header

                if let dashboard = appState.dashboard {
                    metricsGrid(for: dashboard)
                } else {
                    disconnectedState
                }
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(minWidth: 480, minHeight: 420)
        .task {
            appState.startPolling()
        }
        .onDisappear {
            appState.stopPolling()
        }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Broker Sakuma").font(.largeTitle.bold())
                StatusBadge(state: appState.dashboard?.systemState ?? .unknown, displayMode: appState.displayMode)
            }
            Spacer()
            Picker("Modo", selection: $appState.displayMode) {
                ForEach(DisplayMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)
            Button {
                openWindow(id: "settings")
            } label: {
                Image(systemName: "gearshape")
            }
            .help("Configurações")
        }
    }

    private var disconnectedState: some View {
        let presentation = appState.lastError.map(BeginnerMessage.present)
        return VStack(alignment: .leading, spacing: 12) {
            Text(presentation?.headline ?? "Ainda não conectado ao sistema.")
                .font(.headline)
            Text("Isso é esperado se o backend local ainda não foi iniciado.")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            if appState.displayMode == .advanced, let presentation {
                DisclosureGroup("Ver detalhes técnicos") {
                    Text(presentation.technicalDetails)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func metricsGrid(for dashboard: DashboardSummary) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 16)], spacing: 16) {
            MetricTile(title: "Capital operacional", value: currency(dashboard.capitalOperationalUsd))
            MetricTile(title: "Reserva", value: currency(dashboard.reserveUsd))
            MetricTile(
                title: "P&L do dia",
                value: currency(dashboard.dailyPnlUsd),
                tint: dashboard.dailyPnlUsd >= 0 ? .green : .red
            )
            MetricTile(
                title: "P&L total",
                value: currency(dashboard.totalPnlUsd),
                tint: dashboard.totalPnlUsd >= 0 ? .green : .red
            )
            MetricTile(title: "Bots ativos", value: "\(dashboard.activeBots)")
            MetricTile(title: "Bots mortos", value: "\(dashboard.deadBots)")
            MetricTile(title: "Ressurreições", value: "\(dashboard.resurrectedBots)")
        }
    }

    private func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "USD"))
    }
}

private struct MetricTile: View {
    let title: String
    var value: String
    var tint: Color = .primary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title2.weight(.semibold))
                .foregroundStyle(tint)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
