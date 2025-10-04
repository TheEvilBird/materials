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

/// Broadcast Homework Tests
#[derive(Parser, Debug)]
#[clap(about, long_about = None)]
struct Args {
    /// Path to Python file with solution
    #[clap(long = "impl", short = 'i', default_value = "solution/broadcast.py")]
    solution_path: String,

    /// Test to run (optional)
    #[clap(long = "test", short)]
    test: Option<String>,

    /// Print execution trace
    #[clap(long, short)]
    debug: bool,

    /// Random seed used in tests
    #[clap(long, short, default_value = "2023")]
    seed: u64,

    /// Number of processes
    #[clap(long, short, default_value = "5")]
    proc_count: u64,

    /// Number of chaos monkey runs
    #[clap(long, short, default_value = "10")]
    monkeys: u32,

    /// Do not run model checking tests
    #[clap(long)]
    disable_mc_tests: bool,
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
    let proc_factory = PyProcessFactory::new(&args.solution_path, "BroadcastProcess");
    let mut config = TestConfig {
        proc_factory: &proc_factory,
        proc_count: args.proc_count,
        seed: args.seed,
        monkeys: args.monkeys,
        debug: args.debug,
    };
    let mut tests = TestSuite::new();

    tests.add("NORMAL", test_normal, config);
    tests.add("SENDER CRASH", test_sender_crash, config);
    tests.add("SENDER CRASH 2", test_sender_crash2, config);
    tests.add("TWO CRASHES", test_two_crashes, config);
    tests.add("TWO CRASHES 2", test_two_crashes2, config);
    tests.add("CAUSAL ORDER", test_causal_order, config);
    tests.add("CHAOS MONKEY", test_chaos_monkey, config);
    tests.add("SCALABILITY", test_scalability, config);

    if !args.disable_mc_tests {
        config.proc_count = 3;
        tests.add(
            "MODEL CHECKING NORMAL DELIVERY",
            test_mc_normal_delivery,
            config,
        );
        tests.add("MODEL CHECKING SENDER CRASH", test_mc_sender_crash, config);
    }

    if args.test.is_none() {
        let (_, results) = tests.run();
        let score = score(results);
        println!("SCORE: {score}\n");
    } else {
        tests.run_test(&args.test.unwrap());
    }
}

fn score(results: BTreeMap<String, TestResult>) -> f32 {
    let mut violated = HashSet::new();
    for (_, result) in results {
        if let Err(e) = result {
            if e.starts_with("Violated") {
                for prop in e.replace("Violated ", "").split(", ") {
                    violated.insert(prop.to_string());
                }
            } else {
                return 0.;
            }
        }
    }
    let violated: HashSet<&str> = violated.iter().map(|s| s.as_str()).collect();
    let base_props = HashSet::from([
        "NO DUPLICATION",
        "NO CREATION",
        "VALIDITY",
        "UNIFORM AGREEMENT",
    ]);
    if violated.is_disjoint(&base_props) {
        if violated.is_empty() {
            7.
        } else {
            5.
        }
    } else {
        0.
    }
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
