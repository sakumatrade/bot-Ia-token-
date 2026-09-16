import XCTest
@testable import BrokerSakuma

final class DashboardModelsTests: XCTestCase {
    func testSystemStateDecodesKnownValues() throws {
        let decoder = JSONDecoder()
        let cases: [(String, SystemState)] = [
            ("\"ONLINE\"", .online),
            ("\"PAUSED\"", .paused),
            ("\"SAFE_HALT\"", .safeHalt),
            ("\"EMERGENCY_STOP\"", .emergencyStop),
        ]
        for (json, expected) in cases {
            let decoded = try decoder.decode(SystemState.self, from: Data(json.utf8))
            XCTAssertEqual(decoded, expected)
        }
    }

    func testSystemStateFallsBackToUnknownInsteadOfCrashing() throws {
        let decoder = JSONDecoder()
        let decoded = try decoder.decode(SystemState.self, from: Data("\"SOME_FUTURE_STATE\"".utf8))
        XCTAssertEqual(decoded, .unknown)
    }

    func testDashboardSummaryDecodesSnakeCaseJSON() throws {
        let json = """
        {
            "system_state": "ONLINE",
            "capital_operational_usd": 123.45,
            "reserve_usd": 10.0,
            "daily_pnl_usd": -2.5,
            "total_pnl_usd": 50.0,
            "active_bots": 3,
            "dead_bots": 1,
            "resurrected_bots": 1
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let summary = try decoder.decode(DashboardSummary.self, from: Data(json.utf8))

        XCTAssertEqual(summary.systemState, .online)
        XCTAssertEqual(summary.capitalOperationalUsd, 123.45)
        XCTAssertEqual(summary.activeBots, 3)
        XCTAssertEqual(summary.deadBots, 1)
    }

    func testFriendlyLabelsNeverExposeRawEnumInSimpleMode() {
        for state: SystemState in [.online, .paused, .safeHalt, .emergencyStop, .unknown] {
            XCTAssertNotEqual(state.friendlyLabel, state.rawValue)
        }
    }
}
