# Testing Guidance

This section serves as a nice and handy summary of the testing strategy described below.

|                               | Unit Test                             | Golden Test                          | Integration Test            |
|-------------------------------|---------------------------------------|--------------------------------------|-----------------------------|
| Scope covered                 | Small                                 | Medium                               | Large                       |
| Execution speed               | Milliseconds                          | Seconds                              | Minutes                     |
| Amount in the codebase        | Hundreds                              | Dozens                               | Handful                     |
| Real environment interaction  | No                                    | No                                   | Yes                         |
| Covers whole user journey     | No                                    | Yes                                  | Yes                         |
| Runs on feature branches      | Yes                                   | Yes                                  | No                          |
| Checks edge cases correctness | Yes                                   | No                                   | No                          |
| Flakiness                     | Low                                   | Low                                  | High                        |
| Main focus                    | A class or function logic correctness | User journey, blast radius of change | GCP integration correctness |

# Test Types

This section lists test types available in XPK. The list is ordered from the most common tests first.

## Unit Test

Unit tests are the most granular and fastest type of test in the XPK’s testing pyramid. They focus on verifying the correctness of the smallest logically isolatable parts of your code, often a single function or method. The primary goal is to ensure that each "unit" performs exactly as intended, covering all possible execution paths and diligently handling edge cases. They run on feature branches and are the most basic check for all your changes.

### Naming Conventions

A well-named unit test acts as living documentation for your codebase. The naming convention for XPK's unit tests should clearly convey three parts:

* **Constant prefix:** Every test method should start with a `test_` prefix.
* **Name of the method/unit under test:** This immediately identifies what functionality is being scrutinized.
* **Scenario under test:** Describes the specific conditions or inputs being applied.

For example, a test name like `test_calculator_add_computes_sum_for_negative_numbers_correctly()` instantly tells you that the add method of the Calculator class is being tested with positive numbers, and the expected outcome is a correct sum.

### Developer guide to Unit Tests

Unit tests are co-located with the production code. Specifically, the test file for any given module will bear the same name as the module, appended with a `_test.py` suffix (e.g., `gcloud_command.py` will have its tests in `gcloud_command_test.py`). When implementing new features or modifying existing code, it is imperative to ensure that corresponding unit tests are updated and added as necessary. These unit tests are automatically discovered among all `_test.py` files and can be executed using the `make run-unittests` command.

### Isolating Units with Mocks and Fakes

A crucial aspect of effective unit testing is isolation. A unit test should only be concerned with the behavior of the specific unit it is testing, without being influenced by its dependencies (e.g., databases, external services, or complex objects). To achieve this, unit tests often utilize mocks or fake classes.

* Mocks are "test doubles" that simulate the behavior of real dependencies. They allow you to define what methods should be called, with what arguments, and what values they should return. This gives you complete control over the unit's environment and allows you to test specific interactions. The mocks are defined using pytest-mock library.
* Fake classes are simplified, in-memory implementations of actual dependencies. They provide a working (though often simplified) version of the dependency's functionality, making them useful when you need a more substantial stand-in than a simple mock.

### Unit Test Sample

A good, state-of-the-art sample of [code](https://github.com/AI-Hypercomputer/xpk/blob/0434cf6a023069522f90d5846c6d980b68382b66/src/xpk/core/nodepool.py#L614) that has been correctly covered with unit tests can be found [here](https://github.com/AI-Hypercomputer/xpk/blob/8464ce26cd0fd24c681e346b2c915ad918724e53/src/xpk/core/nodepool_test.py#L26). This provided example serves as a practical guide and "source of truth" for developers, demonstrating best practices in unit test structure like naming. Another sample, leveraging mocks could be found [here](https://github.com/AI-Hypercomputer/xpk/blob/8464ce26cd0fd24c681e346b2c915ad918724e53/src/xpk/core/nodepool_test.py#L86).

## Golden Test

Golden tests encompass a broad scope within XPK, effectively covering the entire execution of a command from a user's perspective. Their primary objective is to highlight the blast radius of a change by making developers aware of all user journeys that might be affected by the change. These tests are executed on feature branches and serve as the main tool for raising awareness, enabling developers to thoroughly double-check changes across various scenarios and understand their potential impact.

### Naming Conventions

Each Golden test name should refer to a potential use case or persona utilizing the system, explicitly including the command that is executed. This approach ensures that the test names clearly communicate the real-world scenarios and user interactions they validate, focusing on the actions taken. A good Golden test name should typically convey:

* **Command name that is executed:** cluster create, cluster create-pathways, or workload list.
* **Use case it is covering:** nap cluster creation, tpu cluster creation, workload status listing

For example, a good golden test name could be: "NAP cluster-create with pathways".

### Developer guide to Golden Tests
All golden tests are registered in the `goldens.yaml` file in the root directory. Their reference output is stored in text files located in goldens directory in the root directory.

A sample structure of `goldens.yaml` file is defined as:

```yaml
goldens:
  "NAP cluster-create with pathways":
    command: xpk cluster create-pathways --enable-autoprovisioning
    description: "" # optional description allowing to better understand use-case
```

Goldens after change in the code, or registering a new one can be re-generated using `make goldens` command.

### Underlying execution mechanisms

These tests are executed through the GoldenBuddy testing script located in the `golden_buddy.sh` file of the repository. The framework executes all registered commands in `dry_run` mode, then compares diffs between them with the reference output located in goldens directory.

## Integration Test
Integration tests sit at the apex of the testing pyramid, being the most expensive and slowest to execute. This is primarily because they rely on actual Google Cloud Platform (GCP) infrastructure, which introduces potential flakiness due to external factors and makes it challenging to write given capacity constraints. Consequently, these tests should be reserved for ultimate verification before release, ensuring all of XPK's components function seamlessly together within a real GCP environment. They are not run on feature branches; instead, they are executed on the mainline (`main`) branch nightly after code merges, and right before a release to validate a new XPK release candidate. This strategic placement ensures a final, comprehensive check of the entire system's functionality in its production-like setting.

### Naming Conventions

Similarly to goldens, each integration test name should refer to a potential use case or persona utilizing the system, explicitly including the command that is executed. This approach ensures that the test names clearly communicate the real-world scenarios and user interactions they validate, focusing on the actions taken. A good Golden test name should typically convey:

* **Command name that is executed:** cluster create, cluster create-pathways, or workload list.
* **Use case it is covering:** nap cluster creation, tpu cluster creation, workload status listing

For example, an integration golden test name could be: "NAP cluster-create with pathways".

### Developer guide to Integration Tests

Integration tests are managed within our GitHub Actions definitions. To promote reusability and maintainability, each covered scenario is stored in its own dedicated file, following a reusable actions pattern. These individual scenario files are then orchestrated within a single, central configuration file, designed to execute whenever a release is performed or nightly on the mainline branch.

### Underlying execution mechanisms

To ensure these tests genuinely reflect the end-user experience, they operate on the final XPK artifact (a wheel package). This crucial design choice means the tests do not directly interact with the code in the repository itself. Instead, they simulate how an end-user would install the XPK via pip or other Python package managers, creating an environment that closely mirrors real-world usage.

Furthermore, to combat the dreaded "flakiness" often associated with integration tests and significantly boost their success rate, we have implemented a robust backoff retry mechanism. This automatically retries failed tests after a delay, increasing the probability of a successful run and providing more reliable feedback.
