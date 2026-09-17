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

    func testBotSummaryDecodesSnakeCaseJSONIgnoringExtraFields() throws {
        let json = """
        {
            "id": "abc-123",
            "name": "Son 001",
            "version": "1",
            "state": "ACTIVE",
            "generation": 1,
            "parent_id": "mother-id",
            "capital_operational_usd": 5.0,
            "reserve_usd": 0.0,
            "capital_borrowed_usd": 5.0,
            "cumulative_pnl_usd": 1.25,
            "drawdown_pct": 0.0,
            "trades_count": 4,
            "theses_tested_count": 1
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let bot = try decoder.decode(BotSummary.self, from: Data(json.utf8))

        XCTAssertEqual(bot.id, "abc-123")
        XCTAssertEqual(bot.name, "Son 001")
        XCTAssertEqual(bot.state, "ACTIVE")
        XCTAssertEqual(bot.parentId, "mother-id")
        XCTAssertEqual(bot.capitalOperationalUsd, 5.0)
        XCTAssertEqual(bot.cumulativePnlUsd, 1.25)
        XCTAssertEqual(bot.tradesCount, 4)
    }

    func testBotSummaryDecodesNilParentIdForAMotherBot() throws {
        let json = """
        {
            "id": "mother-id", "name": "Mother Bot", "version": "1", "state": "ACTIVE",
            "generation": 0, "parent_id": null, "capital_operational_usd": 1000.0,
            "reserve_usd": 0.0, "capital_borrowed_usd": 0.0, "cumulative_pnl_usd": 0.0,
            "drawdown_pct": 0.0, "trades_count": 0, "theses_tested_count": 0
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let bot = try decoder.decode(BotSummary.self, from: Data(json.utf8))

        XCTAssertNil(bot.parentId)
    }

    func testAutoTradingStatusDecodesSnakeCaseJSON() throws {
        let json = """
        {
            "enabled": true,
            "running": true,
            "interval_seconds": 10.0,
            "launches_per_cycle": 1,
            "position_fraction_of_capital": 0.5
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let status = try decoder.decode(AutoTradingStatus.self, from: Data(json.utf8))

        XCTAssertTrue(status.enabled)
        XCTAssertTrue(status.running)
        XCTAssertEqual(status.intervalSeconds, 10.0)
        XCTAssertEqual(status.launchesPerCycle, 1)
        XCTAssertEqual(status.positionFractionOfCapital, 0.5)
    }
}
