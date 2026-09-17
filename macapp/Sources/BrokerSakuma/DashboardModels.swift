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

/// Mirrors `api/schemas.py`'s `RiskPolicySummary` ("Dominus Risk" — the
/// limits every simulated order already passes through). Read-only:
/// nothing in this app ever changes these values.
struct RiskPolicySummary: Codable, Equatable {
    let maxPositionUsd: Double
    let maxDailyLossUsd: Double
    let maxDrawdownPct: Double
    let maxSlippagePct: Double
    let minLiquidityUsd: Double
    let maxTradesPerDay: Int
    let maxConsecutiveLosses: Int
    let minWalletBalanceUsd: Double
    let perBotMaxLossUsd: Double
    let perBotMaxLossPctOfCapital: Double?
}

/// Mirrors `api/schemas.py`'s `ReserveSummary` (Dominus Treasury).
struct ReserveSummary: Codable, Equatable, Identifiable {
    let id: String
    let botId: String?
    let balanceUsd: Double
}

/// Mirrors `api/schemas.py`'s `BotLoanSummary` (Dominus Treasury) — only
/// the fields this app displays.
struct BotLoanSummary: Codable, Equatable, Identifiable {
    let id: String
    let loanId: String
    let interestModel: String
    let status: String
    let remainingBalanceUsd: Double
}

/// Mirrors `api/schemas.py`'s `ProtocolSummary` (Dominus Lab) — only the
/// fields this app displays; extra backend fields decode fine and are
/// ignored.
struct ProtocolSummary: Codable, Equatable, Identifiable {
    let id: String
    let name: String
    let blockchain: String
    let status: String
    let riskScore: Double?
}

/// Mirrors `api/schemas.py`'s `LearningEventSummary` (Dominus Network) —
/// what bots have broadcast to each other, spec section 9.
struct LearningEventSummary: Codable, Equatable, Identifiable {
    let id: String
    let kind: String
    let title: String
}

/// Mirrors `api/schemas.py`'s `PatternInsightSummary` (Dominus AI) —
/// what PatternLearner has actually learned so far, spec section 26.
struct PatternInsightSummary: Codable, Equatable, Identifiable {
    var id: String { liquidityBucketTag }
    let liquidityBucketTag: String
    let samplesCount: Int
    let averagePnlUsd: Double
    let confidenceMultiplier: Double
}
