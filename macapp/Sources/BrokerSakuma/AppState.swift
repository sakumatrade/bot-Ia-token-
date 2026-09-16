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
    @Published private(set) var dashboard: DashboardSummary?
    @Published private(set) var lastError: Error?
    @Published private(set) var isLoading = false
    @Published var displayMode: DisplayMode = .simple

    private let apiClient: APIClient
    private var pollTask: Task<Void, Never>?
    private let pollIntervalNanoseconds: UInt64

    init(apiClient: APIClient = APIClient(), pollIntervalSeconds: UInt64 = 5) {
        self.apiClient = apiClient
        self.pollIntervalNanoseconds = pollIntervalSeconds * 1_000_000_000
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
        isLoading = true
        defer { isLoading = false }
        do {
            dashboard = try await apiClient.fetchDashboard()
            lastError = nil
        } catch {
            // A failed refresh never keeps stale data around pretending
            // it's live — Advanced/Simple Mode alike show "disconnected".
            dashboard = nil
            lastError = error
        }
    }

    func sendSystemAction(_ action: SystemAction) async {
        do {
            try await apiClient.sendSystemAction(action)
            lastError = nil
            await refresh()
        } catch {
            lastError = error
        }
    }
}
