import asyncio
import itertools
import json
import time

import src.constants
import src.hashstack
import src.helpers
import src.histogram
import src.loans_table
import src.main_chart
import src.nostra
import src.nostra_uncapped
import src.persistent_state
import src.protocol_stats
import src.swap_liquidity
import src.zklend



def update_data(zklend_state):
    t0 = time.time()
    print(f"Updating CSV data from {zklend_state.last_block_number}...", flush=True)
    zklend_events = src.zklend.get_events(start_block_number = zklend_state.last_block_number + 1)
    hashstack_events = src.hashstack.get_events()
    nostra_events = src.nostra.get_events()
    nostra_uncapped_events = src.nostra_uncapped.get_events()
    print(f"got events in {time.time() - t0}s", flush=True)

    t1 = time.time()

    # Iterate over ordered events to obtain the final state of each user.
    for _, zklend_event in zklend_events.iterrows():
        zklend_state.process_event(event=zklend_event)

    hashstack_state = src.hashstack.HashstackState()
    for _, hashstack_event in hashstack_events.iterrows():
        hashstack_state.process_event(event=hashstack_event)

    nostra_state = src.nostra.NostraState()
    for _, nostra_event in nostra_events.iterrows():
        nostra_state.process_event(event=nostra_event)

    nostra_uncapped_state = src.nostra_uncapped.NostraUncappedState()
    for _, nostra_uncapped_event in nostra_uncapped_events.iterrows():
        nostra_uncapped_state.process_event(event=nostra_uncapped_event)

    print(f"updated state in {time.time() - t1}s", flush=True)

    t_prices = time.time()
    prices = src.swap_liquidity.Prices()

    print(f"prices in {time.time() - t_prices}s", flush=True)

    t_swap = time.time()

    swap_amms = asyncio.run(src.swap_liquidity.SwapAmm().init())

    print(f"swap in {time.time() - t_swap}s", flush=True)

    t2 = time.time()

    states = [zklend_state, hashstack_state, nostra_state, nostra_uncapped_state]
    for pair, state in itertools.product(src.constants.PAIRS, states):
        # TODO: Decipher `pair` in a smarter way.
        collateral_token, borrowings_token = pair.split("-")
        _ = src.main_chart.get_main_chart_data(
            state=state,
            prices=prices.prices,
            swap_amms=swap_amms,
            collateral_token=collateral_token,
            debt_token=borrowings_token,
            save_data=True,
        )
        print(f"Main chart data for pair = {pair} prepared in {time.time() - t2}s", flush=True)

    print(f"updated graphs in {time.time() - t2}s", flush=True)

    for state in states:
        _ = src.histogram.get_histogram_data(state=state, prices=prices.prices, save_data=True)

    loan_stats = {}
    for state in states:
        protocol = src.helpers.get_protocol(state=state)
        loan_stats[protocol] = src.loans_table.get_loans_table_data(state=state, prices=prices.prices, save_data=True)

    general_stats = src.protocol_stats.get_general_stats(states=states, loan_stats=loan_stats, save_data=True)
    supply_stats = src.protocol_stats.get_supply_stats(states=states, prices=prices.prices, save_data=True)
    _ = src.protocol_stats.get_collateral_stats(states=states, save_data=True)
    debt_stats = src.protocol_stats.get_debt_stats(states=states, save_data=True)
    _ = src.protocol_stats.get_utilization_stats(
        general_stats=general_stats,
        supply_stats=supply_stats, 
        debt_stats=debt_stats, 
        save_data=True,
    )

    max_block_number = zklend_events["block_number"].max()
    max_timestamp = zklend_events["timestamp"].max()

    dict = {"timestamp": str(max_timestamp),
            "block_number": str(max_block_number)}

    with open("zklend_data/last_update.json", "w") as outfile:
        outfile.write(json.dumps(dict))

    print(f"Updated CSV data in {time.time() - t0}s", flush=True)
    return zklend_state


def update_data_continuously():
    state = src.persistent_state.download_and_load_state_from_pickle()
    while True:
        state = update_data(state)
        src.persistent_state.upload_state_as_pickle(state)
        print("DATA UPDATED", flush=True)
        time.sleep(120)


if __name__ == "__main__":
    update_data(src.zklend.ZkLendState())
