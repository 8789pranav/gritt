"""
Master Test Runner for Logic API
Runs all test suites and generates comprehensive report
"""

import subprocess
import sys
import time
from datetime import datetime
import json


def print_header(title):
    """Print formatted header"""
    print("\n" + "="*100)
    print(f"  {title}")
    print("="*100 + "\n")


def run_test_script(script_name, description):
    """Run a test script and capture results"""
    print_header(f"Running: {description}")
    print(f"Script: {script_name}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    start_time = time.time()
    
    try:
        # Run the test script
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        duration = time.time() - start_time
        
        # Print output
        print(result.stdout)
        
        if result.stderr:
            print("\n⚠️  STDERR Output:")
            print(result.stderr)
        
        # Determine success
        success = result.returncode == 0
        
        print(f"\n{'✅ PASSED' if success else '❌ FAILED'} - Duration: {duration:.2f}s")
        
        return {
            "script": script_name,
            "description": description,
            "success": success,
            "duration": duration,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
        
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        print(f"\n❌ TIMEOUT - Test exceeded 5 minutes")
        return {
            "script": script_name,
            "description": description,
            "success": False,
            "duration": duration,
            "return_code": -1,
            "error": "Timeout"
        }
    except Exception as e:
        duration = time.time() - start_time
        print(f"\n❌ ERROR - {str(e)}")
        return {
            "script": script_name,
            "description": description,
            "success": False,
            "duration": duration,
            "return_code": -1,
            "error": str(e)
        }


def generate_report(results):
    """Generate comprehensive test report"""
    print_header("COMPREHENSIVE TEST REPORT")
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["success"])
    failed_tests = total_tests - passed_tests
    total_duration = sum(r["duration"] for r in results)
    
    # Summary table
    print("📊 Test Suite Summary")
    print("-" * 100)
    print(f"{'Test Suite':<50} {'Status':<15} {'Duration':<15}")
    print("-" * 100)
    
    for result in results:
        status = "✅ PASSED" if result["success"] else "❌ FAILED"
        duration = f"{result['duration']:.2f}s"
        description = result["description"][:48]
        print(f"{description:<50} {status:<15} {duration:<15}")
    
    print("-" * 100)
    print(f"{'TOTAL':<50} {passed_tests}/{total_tests} passed {total_duration:.2f}s")
    print("-" * 100)
    
    # Detailed statistics
    print(f"\n📈 Statistics:")
    print(f"   Total Test Suites: {total_tests}")
    print(f"   Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
    print(f"   Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
    print(f"   Total Duration: {total_duration:.2f}s ({total_duration/60:.2f} minutes)")
    print(f"   Average Duration: {total_duration/total_tests:.2f}s per suite")
    
    # Failed tests details
    if failed_tests > 0:
        print(f"\n❌ Failed Test Details:")
        for result in results:
            if not result["success"]:
                print(f"\n   Suite: {result['description']}")
                print(f"   Script: {result['script']}")
                print(f"   Return Code: {result.get('return_code', 'N/A')}")
                if "error" in result:
                    print(f"   Error: {result['error']}")
    
    # Overall result
    print("\n" + "="*100)
    if passed_tests == total_tests:
        print("🎉 ALL TEST SUITES PASSED! 🎉")
        print("="*100)
        return True
    else:
        print(f"⚠️  {failed_tests} TEST SUITE(S) FAILED")
        print("="*100)
        return False


def save_report_to_file(results):
    """Save test results to JSON file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"logic_test_report_{timestamp}.json"
    
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "total_suites": len(results),
        "passed": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "total_duration": sum(r["duration"] for r in results),
        "results": results
    }
    
    try:
        with open(filename, 'w') as f:
            json.dump(report_data, f, indent=2)
        print(f"\n💾 Detailed report saved to: {filename}")
        return filename
    except Exception as e:
        print(f"\n⚠️  Could not save report: {str(e)}")
        return None


def main():
    """Main test runner"""
    print("\n" + "🚀"*50)
    print("LOGIC API COMPREHENSIVE TEST SUITE")
    print("🚀"*50)
    print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version}")
    
    # Define test suites
    test_suites = [
        ("test_logic_comprehensive.py", "Comprehensive Logic API Test (Full Workflow)"),
        ("test_logic_all_grades.py", "Multi-Grade Logic API Test (All Grades)"),
        ("test_logic_edge_cases.py", "Edge Cases & Error Handling Test"),
    ]
    
    # Check if all test files exist
    import os
    missing_files = []
    for script, _ in test_suites:
        if not os.path.exists(script):
            missing_files.append(script)
    
    if missing_files:
        print(f"\n❌ ERROR: Missing test files:")
        for f in missing_files:
            print(f"   - {f}")
        print("\nPlease ensure all test scripts are in the current directory.")
        return 1
    
    print(f"\n📋 Test Plan:")
    for i, (script, description) in enumerate(test_suites, 1):
        print(f"   {i}. {description}")
    
    input("\n⏸️  Press Enter to start testing...")
    
    # Run all test suites
    results = []
    for script, description in test_suites:
        result = run_test_script(script, description)
        results.append(result)
        time.sleep(2)  # Brief pause between suites
    
    # Generate and display report
    all_passed = generate_report(results)
    
    # Save report to file
    save_report_to_file(results)
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Return appropriate exit code
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
