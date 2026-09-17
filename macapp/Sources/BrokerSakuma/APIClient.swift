import Foundation

/// System actions exposed by the (future) Local API POST endpoints
/// (spec section 38): `/api/system/{start,pause,resume,kill-switch}`.
enum SystemAction: String {
    case start
    case pause
    case resume
    case killSwitch = "kill-switch"
}

/// Talks to the DominusBot Local API. Never fabricates a response: any
/// failure to reach the backend or parse its response surfaces as a typed
/// `APIError`, which the UI maps to a beginner-friendly message and a
/// safe "disconnected" state — it never falls back to fake/simulated
/// numbers just to have something to show.
actor APIClient {
    /// The Local API's default address (spec section 38) — also what the
    /// dashboard's "Abrir painel no navegador" button opens, so the two
    /// never drift apart.
    static let defaultBaseURL = URL(string: "http://127.0.0.1:8765")!

    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL = APIClient.defaultBaseURL) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 5
        self.session = URLSession(configuration: configuration)
    }

    func fetchDashboard(apiKey: String) async throws -> DashboardSummary {
        let data = try await get(path: "api/dashboard", apiKey: apiKey)
        return try decode(DashboardSummary.self, from: data)
    }

    func sendSystemAction(_ action: SystemAction, apiKey: String) async throws {
        _ = try await post(path: "api/system/\(action.rawValue)", apiKey: apiKey)
    }

    func fetchBots(apiKey: String) async throws -> [BotSummary] {
        let data = try await get(path: "api/bots", apiKey: apiKey)
        return try decode([BotSummary].self, from: data)
    }

    func fetchAutoTradingStatus(apiKey: String) async throws -> AutoTradingStatus {
        let data = try await get(path: "api/system/auto-trading", apiKey: apiKey)
        return try decode(AutoTradingStatus.self, from: data)
    }

    /// "Dominus Risk": the limits every simulated order already passes
    /// through, read-only — works fine with the read-only viewer key too.
    func fetchRiskPolicy(apiKey: String) async throws -> RiskPolicySummary {
        let data = try await get(path: "api/system/risk-policy", apiKey: apiKey)
        return try decode(RiskPolicySummary.self, from: data)
    }

    /// "Dominus Treasury": reserve balances (spec section 19).
    func fetchReserves(apiKey: String) async throws -> [ReserveSummary] {
        let data = try await get(path: "api/reserves", apiKey: apiKey)
        return try decode([ReserveSummary].self, from: data)
    }

    /// "Dominus Treasury": internal loans from the Dominus Core to its
    /// bots (spec section 17).
    func fetchLoans(apiKey: String) async throws -> [BotLoanSummary] {
        let data = try await get(path: "api/loans", apiKey: apiKey)
        return try decode([BotLoanSummary].self, from: data)
    }

    /// "Dominus Lab": protocols the Research Lab has discovered and
    /// scored (spec section 24/25).
    func fetchProtocols(apiKey: String) async throws -> [ProtocolSummary] {
        let data = try await get(path: "api/protocols", apiKey: apiKey)
        return try decode([ProtocolSummary].self, from: data)
    }

    /// "Dominus Network": broadcasts between bots and council verdicts
    /// (spec section 9). Caller trims to however many rows it displays -
    /// `get(path:)` uses `appendingPathComponent`, which would mangle a
    /// literal "?limit=" query string, so this fetches the (bounded-by-
    /// the-backend-default) full list instead of trying to pass one.
    func fetchLearningEvents(apiKey: String) async throws -> [LearningEventSummary] {
        let data = try await get(path: "api/learning-events", apiKey: apiKey)
        return try decode([LearningEventSummary].self, from: data)
    }

    /// "Dominus AI": what PatternLearner has actually learned so far
    /// (spec section 26).
    func fetchPatternInsights(apiKey: String) async throws -> [PatternInsightSummary] {
        let data = try await get(path: "api/pattern-insights", apiKey: apiKey)
        return try decode([PatternInsightSummary].self, from: data)
    }

    func setAutoTrading(enabled: Bool, apiKey: String) async throws -> AutoTradingStatus {
        let data = try await post(path: "api/system/auto-trading", apiKey: apiKey, jsonBody: ["enabled": enabled])
        return try decode(AutoTradingStatus.self, from: data)
    }

    func pauseBot(id: String, apiKey: String) async throws {
        _ = try await post(path: "api/bots/\(id)/pause", apiKey: apiKey)
    }

    func resumeBot(id: String, apiKey: String) async throws {
        _ = try await post(path: "api/bots/\(id)/resume", apiKey: apiKey)
    }

    /// Creates the Dominus Core if one doesn't exist yet, spawns a Son, and
    /// activates it — funding it with the fixed $5 simulated stake (spec
    /// section 10's $5 rule). The same three endpoints
    /// `scripts/activate_bot.sh` and the browser dashboard's "Criar bot"
    /// card already use over curl/fetch; no wallet or blockchain call
    /// anywhere in this flow.
    func createAndActivateBot(name: String?, motherInitialCapitalUsd: Double, apiKey: String) async throws -> BotSummary {
        let existingBots = try await fetchBots(apiKey: apiKey)
        let motherId: String
        if let existingMother = existingBots.first(where: { $0.parentId == nil }) {
            motherId = existingMother.id
        } else {
            let motherData = try await post(
                path: "api/bots/mother",
                apiKey: apiKey,
                jsonBody: ["name": "Dominus Core", "initial_capital_usd": motherInitialCapitalUsd]
            )
            motherId = try decode(BotSummary.self, from: motherData).id
        }

        var sonBody: [String: Any] = ["parent_id": motherId]
        if let name, !name.isEmpty {
            sonBody["name"] = name
        }
        let sonData = try await post(path: "api/bots/sons", apiKey: apiKey, jsonBody: sonBody)
        let son = try decode(BotSummary.self, from: sonData)

        _ = try await post(path: "api/bots/\(son.id)/activate", apiKey: apiKey)
        return son
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            return try decoder.decode(type, from: data)
        } catch {
            throw APIError.decodingFailed
        }
    }

    private func get(path: String, apiKey: String) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "GET"
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        return try await perform(request)
    }

    private func post(path: String, apiKey: String) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        return try await perform(request)
    }

    private func post(path: String, apiKey: String, jsonBody: [String: Any]) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: jsonBody)
        return try await perform(request)
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.notConnected
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.notConnected
        }

        switch httpResponse.statusCode {
        case 200..<300:
            return data
        case 401, 403:
            throw APIError.unauthorized
        default:
            throw APIError.serverError(statusCode: httpResponse.statusCode)
        }
    }
}
