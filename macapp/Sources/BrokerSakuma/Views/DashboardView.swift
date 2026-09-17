import Foundation
import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.openWindow) private var openWindow
    @Environment(\.openURL) private var openURL
    @State private var newBotName: String = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                simulationBanner
                header

                if let dashboard = appState.dashboard {
                    metricsGrid(for: dashboard)
                    createBotSection
                    botsSection
                    autoTradingSection
                    riskPolicySection
                    treasurySection
                    labSection
                    networkSection
                    aiSection
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

    private var simulationBanner: some View {
        Text("🧪 Modo de teste")
            .font(.caption.weight(.semibold))
            .foregroundStyle(.black)
            .frame(maxWidth: .infinity)
            .padding(8)
            .background(Color.yellow)
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("DominusBot").font(.largeTitle.bold())
                Text("AI Multi-Agent Trading & Research Platform")
                    .font(.caption)
                    .foregroundStyle(.secondary)
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
                openURL(APIClient.defaultBaseURL.appendingPathComponent("dashboard"))
            } label: {
                Image(systemName: "safari")
            }
            .help("Abrir o painel no navegador")
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

    /// Creates the Dominus Core if missing, spawns a Son, and activates it
    /// with the fixed $5 simulated stake — same as `scripts/activate_bot.sh`
    /// and the browser dashboard's "Criar bot" card. Simulated capital
    /// only; see `docs/ARCHITECTURE.md#security`.
    private var createBotSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Criar bot").font(.headline)
            HStack {
                TextField("Nome do novo bot (opcional)", text: $newBotName)
                    .textFieldStyle(.roundedBorder)
                Button {
                    let name = newBotName
                    newBotName = ""
                    Task { await appState.createBot(name: name.isEmpty ? nil : name) }
                } label: {
                    Label("Criar e ativar", systemImage: "plus.circle")
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var botsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("O que o bot está fazendo").font(.headline)
            if appState.bots.isEmpty {
                Text("Nenhum bot criado ainda.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(appState.bots) { bot in
                    botRow(bot)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func botRow(_ bot: BotSummary) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(bot.name).font(.body.weight(.medium))
                Text("\(bot.state) · \(currency(bot.capitalOperationalUsd))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            // The Dominus Core (no parent) is never individually paused —
            // pausing takes a Son out of the autonomous loop, mirroring
            // POST /api/bots/{id}/pause's own restriction.
            if bot.parentId != nil, bot.state != "DEAD" {
                Button(bot.state == "PAUSED" ? "Retomar" : "Pausar") {
                    Task {
                        if bot.state == "PAUSED" {
                            await appState.resumeBot(id: bot.id)
                        } else {
                            await appState.pauseBot(id: bot.id)
                        }
                    }
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(.vertical, 4)
    }

    private var autoTradingSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Operação automática (simulada)").font(.headline)
            Text("Quando ligada, todo bot ACTIVE observa e opera sozinho — sempre com dinheiro simulado.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Toggle(isOn: Binding(
                get: { appState.autoTradingStatus?.enabled ?? false },
                set: { newValue in Task { await appState.toggleAutoTrading(enabled: newValue) } }
            )) {
                Text(appState.autoTradingStatus?.enabled == true ? "Ligada" : "Desligada")
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    /// "Dominus Risk": the limits every simulated order already passes
    /// through (RiskEngine + MaximumLossPolicy), shown read-only — this
    /// app never changes them, it only displays what protects the
    /// simulated capital.
    private var riskPolicySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Dominus Risk").font(.headline)
            Text("Limites de segurança que toda operação simulada já passa por baixo dos panos.")
                .font(.caption)
                .foregroundStyle(.secondary)
            if let policy = appState.riskPolicy {
                VStack(alignment: .leading, spacing: 4) {
                    riskRow("Tamanho máximo por operação", currency(policy.maxPositionUsd))
                    riskRow("Perda máxima permitida por dia", currency(policy.maxDailyLossUsd))
                    riskRow("Queda máxima tolerada (drawdown)", percent(policy.maxDrawdownPct))
                    riskRow("Deslizamento de preço máximo aceito", percent(policy.maxSlippagePct))
                    riskRow("Liquidez mínima exigida do lançamento", currency(policy.minLiquidityUsd))
                    riskRow("Operações máximas por dia", "\(policy.maxTradesPerDay)")
                    riskRow("Perdas seguidas máximas antes de parar", "\(policy.maxConsecutiveLosses)")
                    riskRow("Saldo mínimo exigido da carteira", currency(policy.minWalletBalanceUsd))
                    riskRow("Perda máxima de um bot (o que o mata)", currency(policy.perBotMaxLossUsd))
                }
            } else {
                Text("Carregando…").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func riskRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.caption.weight(.medium))
        }
    }

    private func percent(_ value: Double) -> String {
        (value).formatted(.percent.precision(.fractionLength(0)))
    }

    /// Dominus Treasury: reserve balance + internal loans from the
    /// Dominus Core to its bots (spec sections 17, 19) - the same
    /// simulated numbers already shown as "Reserva" above, just grouped
    /// with loan detail.
    private var treasurySection: some View {
        let totalReserve = appState.reserves.reduce(0) { $0 + $1.balanceUsd }
        let activeLoans = appState.loans.filter { $0.status != "PAID_OFF" && $0.status != "DEFAULTED" }
        return VStack(alignment: .leading, spacing: 8) {
            Text("Dominus Treasury").font(.headline)
            Text("Reserva total: \(currency(totalReserve))").font(.caption)
            if activeLoans.isEmpty {
                Text("Nenhum empréstimo ativo no momento.").font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(activeLoans) { loan in
                    riskRow(loan.loanId, currency(loan.remainingBalanceUsd) + " restantes")
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    /// Dominus Lab: protocols the Research Lab has discovered and scored
    /// (spec sections 24/25).
    private var labSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Dominus Lab").font(.headline)
            if appState.protocols.isEmpty {
                Text("Nenhum protocolo pesquisado ainda.").font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(appState.protocols.prefix(10)) { protocolItem in
                    riskRow(protocolItem.name, protocolItem.status)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    /// Dominus Network: what bots have broadcast to each other, including
    /// council verdicts (spec section 9) - an opinion, even a unanimous
    /// one, is never shown as a fact.
    private var networkSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Dominus Network").font(.headline)
            if appState.learningEvents.isEmpty {
                Text("Nenhuma troca entre bots ainda.").font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(appState.learningEvents.prefix(10)) { event in
                    Text(event.title).font(.caption)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    /// Dominus AI: what PatternLearner has actually learned from real
    /// (simulated) outcomes so far (spec section 26) - the exact same
    /// data already nudging position sizing, never a bigger claim.
    private var aiSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Dominus AI").font(.headline)
            if appState.patternInsights.isEmpty {
                Text("Ainda sem aprendizado suficiente.").font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(appState.patternInsights) { insight in
                    riskRow(
                        "\(insight.samplesCount) operações",
                        currency(insight.averagePnlUsd) + " médio · \(String(format: "%.2f", insight.confidenceMultiplier))x"
                    )
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
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
