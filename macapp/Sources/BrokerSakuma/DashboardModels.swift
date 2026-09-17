import Foundation

/// Mirrors `broker_sakuma.core.enums.SystemState` on the backend
/// (spec section 6). Kept as a plain string enum so an unknown future
/// value from the backend decodes as `.unknown` instead of crashing.
enum SystemState: String, Codable, Equatable {
    case online = "ONLINE"
    case paused = "PAUSED"
    case safeHalt = "SAFE_HALT"
    case emergencyStop = "EMERGENCY_STOP"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = SystemState(rawValue: raw) ?? .unknown
    }

    /// Beginner-facing label (Simple Mode never shows the raw enum name).
    var friendlyLabel: String {
        switch self {
        case .online: return "Funcionando normalmente"
        case .paused: return "Pausado"
        case .safeHalt: return "Parado por segurança"
        case .emergencyStop: return "Parada de emergência"
        case .unknown: return "Estado desconhecido"
        }
    }
}

/// Mirrors the shape the future `/api/dashboard` endpoint (spec section 38)
/// is expected to return. This is a client-side contract only — nothing
/// here invents values; every field is optional-safe at the call site via
/// `AppState.dashboard == nil` while disconnected.
struct DashboardSummary: Codable, Equatable {
    let systemState: SystemState
    let capitalOperationalUsd: Double
    let reserveUsd: Double
    let dailyPnlUsd: Double
    let totalPnlUsd: Double
    let activeBots: Int
    let deadBots: Int
    let resurrectedBots: Int
}

/// Mirrors `api/schemas.py`'s `BotSummary` — only the fields this app
/// actually displays; extra backend fields decode fine and are ignored.
struct BotSummary: Codable, Equatable, Identifiable {
    let id: String
    let name: String
    let state: String
    let parentId: String?
    let capitalOperationalUsd: Double
    let cumulativePnlUsd: Double
    let tradesCount: Int
}

/// Mirrors `api/schemas.py`'s `AutoTradingStatusResponse` (spec sections
/// 3, 22, 28's autonomous PAPER-trading loop — never live trading).
struct AutoTradingStatus: Codable, Equatable {
    let enabled: Bool
    let running: Bool
    let intervalSeconds: Double
    let launchesPerCycle: Int
    let positionFractionOfCapital: Double
}
