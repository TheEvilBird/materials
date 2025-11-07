mod common;
mod tests;
mod tests_mc;

use std::collections::{BTreeMap, HashSet};
use std::env;
use std::io::Write;

use clap::Parser;
use env_logger::Builder;
use log::LevelFilter;

use anysystem::python::PyProcessFactory;
use anysystem::test::{TestResult, TestSuite};

use crate::common::TestConfig;
use crate::tests::*;
use crate::tests_mc::*;

/// Sharded KV Store Homework Tests
#[derive(Parser, Debug)]
#[clap(about, long_about = None)]
struct Args {
    /// Path to Python file with solution
    #[clap(long = "impl", short = 'i', default_value = "solution/node.py")]
    solution_path: String,

    /// Test to run (optional)
    #[clap(long = "test", short)]
    test: Option<String>,

    /// Print execution trace
    #[clap(long, short)]
    debug: bool,

    /// Number of nodes used in tests
    #[clap(long, short, default_value = "10")]
    node_count: u32,

    /// Random seed used in tests
    #[clap(long, short, default_value = "123")]
    seed: u64,
}

fn main() {
    let args = Args::parse();
    if args.debug {
        Builder::new()
            .filter(Some("anysystem"), LevelFilter::Debug)
            .format(|buf, record| writeln!(buf, "{}", record.args()))
            .init();
    }
    append_to_python_path("../../anysystem/python".to_string());
    env::set_var("PYTHONHASHSEED", args.seed.to_string());
    let process_factory = PyProcessFactory::new(&args.solution_path, "StorageNode");
    let config = TestConfig {
        impl_path: &args.solution_path,
        process_factory: &process_factory,
        proc_count: args.node_count,
        seed: args.seed,
    };
    let mut single_config = config;
    single_config.proc_count = 1;
    let mut mc_config = config;
    mc_config.proc_count = 3;
    let mut tests = TestSuite::new();

    tests.add("SINGLE NODE", test_single_node, single_config);
    tests.add("INSERTS", test_inserts, config);
    tests.add("DELETES", test_deletes, config);
    tests.add("MEMORY OVERHEAD", test_memory_overhead, config);
    tests.add("MC NORMAL", test_mc_normal, mc_config);
    tests.add("NODE ADDED", test_node_added, config);
    tests.add(
        "NODE ADDED DURING INSERTS",
        test_node_added_during_inserts,
        config,
    );
    tests.add("NODE REMOVED", test_node_removed, config);
    tests.add(
        "NODE REMOVED AFTER CRASH",
        test_node_removed_after_crash,
        config,
    );
    tests.add("MC NODE REMOVED", test_mc_node_removed, mc_config);
    tests.add("MIGRATION", test_migration, config);
    tests.add("SCALE UP DOWN", test_scale_up_down, config);
    tests.add("DISTRIBUTION", test_distribution, config);
    tests.add(
        "DISTRIBUTION NODE ADDED",
        test_distribution_node_added,
        config,
    );
    tests.add(
        "DISTRIBUTION NODE REMOVED",
        test_distribution_node_removed,
        config,
    );

    if args.test.is_none() {
        let (_, results) = tests.run();
        let score = score(results);
        println!("\nSCORE: {score}\n");
    } else {
        tests.run_test(&args.test.unwrap());
    }
}

macro_rules! string_set {
    ($($x:expr),+ $(,)?) => (
        HashSet::from([$($x.to_string()),+])
    );
}

fn score(results: BTreeMap<String, TestResult>) -> f32 {
    let basic_group = string_set! {
        "SINGLE NODE", "INSERTS", "DELETES", "MEMORY OVERHEAD", "MC NORMAL"
    };
    let node_changes_group = string_set! {
        "NODE ADDED", "NODE ADDED DURING INSERTS", "NODE REMOVED", "NODE REMOVED AFTER CRASH",
        "MC NODE REMOVED", "MIGRATION", "SCALE UP DOWN"
    };
    let distribution_group = string_set! {
        "DISTRIBUTION", "DISTRIBUTION NODE ADDED", "DISTRIBUTION NODE REMOVED"
    };
    let all_groups = &(&basic_group | &node_changes_group) | &distribution_group;
    assert_eq!(all_groups, results.keys().cloned().collect());

    let mut passed = HashSet::new();
    for (test, result) in results {
        if result.is_ok() {
            passed.insert(test);
        }
    }

    let mut score = 0.;
    print!("Basic tests: ");
    if basic_group.is_subset(&passed) {
        score += 3.;
        println!("passed");
    } else {
        println!("not passed {:?}", basic_group.difference(&passed));
    }
    print!("Node changes tests: ");
    if node_changes_group.is_subset(&passed) {
        if basic_group.is_subset(&passed) {
            score += 3.;
        }
        println!("passed");
    } else {
        println!("not passed {:?}", node_changes_group.difference(&passed));
    }
    print!("Distribution tests: ");
    if distribution_group.is_subset(&passed) {
        if basic_group.is_subset(&passed) {
            score += 2.;
        }
        println!("passed");
    } else {
        println!("not passed {:?}", distribution_group.difference(&passed));
    }
    score
}

fn append_to_python_path(entry: String) {
    let path_separator = if cfg!(windows) { ";" } else { ":" };
    let current_path = env::var("PYTHONPATH").unwrap_or_default();
    let updated_path = if current_path.is_empty() {
        entry
    } else {
        format!("{current_path}{path_separator}{entry}")
    };
    env::set_var("PYTHONPATH", updated_path);
}
