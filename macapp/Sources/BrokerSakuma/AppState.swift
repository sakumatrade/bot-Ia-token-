import Combine
import Foundation

/// Spec section 5: Simple Mode hides technical terms; Advanced Mode shows
/// raw state, logs-adjacent detail, etc.
enum DisplayMode: String, CaseIterable, Identifiable {
    case simple = "Simples"
    case advanced = "Avançado"

    var id: String { rawValue }
}

@MainActor
final class AppState: ObservableObject {
    static let apiKeyDefaultsKey = "brokerSakuma.apiKey"

    @Published private(set) var dashboard: DashboardSummary?
    @Published private(set) var bots: [BotSummary] = []
    @Published private(set) var autoTradingStatus: AutoTradingStatus?
    @Published private(set) var lastError: Error?
    @Published private(set) var isLoading = false
    @Published var displayMode: DisplayMode = .simple
    @Published var apiKey: String {
        didSet {
            UserDefaults.standard.set(apiKey, forKey: Self.apiKeyDefaultsKey)
        }
    }

    private let apiClient: APIClient
    private var pollTask: Task<Void, Never>?
    private let pollIntervalNanoseconds: UInt64

    init(apiClient: APIClient = APIClient(), pollIntervalSeconds: UInt64 = 5) {
        self.apiClient = apiClient
        self.pollIntervalNanoseconds = pollIntervalSeconds * 1_000_000_000
        self.apiKey = UserDefaults.standard.string(forKey: Self.apiKeyDefaultsKey) ?? ""
    }

    var isConnected: Bool { dashboard != nil }

    func startPolling() {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.refresh()
                try? await Task.sleep(nanoseconds: self.pollIntervalNanoseconds)
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        guard !apiKey.isEmpty else {
            dashboard = nil
            lastError = APIError.missingAPIKey
            return
        }

        isLoading = true
        defer { isLoading = false }
        do {
            dashboard = try await apiClient.fetchDashboard(apiKey: apiKey)
            lastError = nil
        } catch {
            // A failed refresh never keeps stale data around pretending
            // it's live — Advanced/Simple Mode alike show "disconnected".
            dashboard = nil
            lastError = error
        }
        await refreshBots()
        await refreshAutoTradingStatus()
    }

    func sendSystemAction(_ action: SystemAction) async {
        guard !apiKey.isEmpty else {
            lastError = APIError.missingAPIKey
            return
        }
        do {
            try await apiClient.sendSystemAction(action, apiKey: apiKey)
            lastError = nil
            await refresh()
        } catch {
            lastError = error
        }
    }

    /// A failed bots/auto-trading refresh is deliberately best-effort: it
    /// doesn't blank out the primary dashboard metrics the way a failed
    /// `refresh()` does — those two lists are secondary to the main
    /// connected/disconnected state.
    func refreshBots() async {
        guard !apiKey.isEmpty else { return }
        if let fetched = try? await apiClient.fetchBots(apiKey: apiKey) {
            bots = fetched
        }
    }

    func refreshAutoTradingStatus() async {
        guard !apiKey.isEmpty else { return }
        if let status = try? await apiClient.fetchAutoTradingStatus(apiKey: apiKey) {
            autoTradingStatus = status
        }
    }

    func createBot(name: String?, motherInitialCapitalUsd: Double = 1000) async {
        guard !apiKey.isEmpty else {
            lastError = APIError.missingAPIKey
            return
        }
        do {
            _ = try await apiClient.createAndActivateBot(name: name, motherInitialCapitalUsd: motherInitialCapitalUsd, apiKey: apiKey)
            lastError = nil
            await refresh()
        } catch {
            lastError = error
        }
    }

    func pauseBot(id: String) async {
        guard !apiKey.isEmpty else { return }
        do {
            try await apiClient.pauseBot(id: id, apiKey: apiKey)
            await refreshBots()
        } catch {
            lastError = error
        }
    }

    func resumeBot(id: String) async {
        guard !apiKey.isEmpty else { return }
        do {
            try await apiClient.resumeBot(id: id, apiKey: apiKey)
            await refreshBots()
        } catch {
            lastError = error
        }
    }

    func toggleAutoTrading(enabled: Bool) async {
        guard !apiKey.isEmpty else { return }
        do {
            autoTradingStatus = try await apiClient.setAutoTrading(enabled: enabled, apiKey: apiKey)
        } catch {
            lastError = error
        }
    }
}
