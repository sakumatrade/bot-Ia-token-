import Foundation

/// System actions exposed by the (future) Local API POST endpoints
/// (spec section 38): `/api/system/{start,pause,resume,kill-switch}`.
enum SystemAction: String {
    case start
    case pause
    case resume
    case killSwitch = "kill-switch"
}

/// Talks to the Broker Sakuma Local API. Never fabricates a response: any
/// failure to reach the backend or parse its response surfaces as a typed
/// `APIError`, which the UI maps to a beginner-friendly message and a
/// safe "disconnected" state — it never falls back to fake/simulated
/// numbers just to have something to show.
actor APIClient {
    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 5
        self.session = URLSession(configuration: configuration)
    }

    func fetchDashboard() async throws -> DashboardSummary {
        let data = try await get(path: "api/dashboard")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            return try decoder.decode(DashboardSummary.self, from: data)
        } catch {
            throw APIError.decodingFailed
        }
    }

    func sendSystemAction(_ action: SystemAction) async throws {
        _ = try await post(path: "api/system/\(action.rawValue)")
    }

    private func get(path: String) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "GET"
        return try await perform(request)
    }

    private func post(path: String) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
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
